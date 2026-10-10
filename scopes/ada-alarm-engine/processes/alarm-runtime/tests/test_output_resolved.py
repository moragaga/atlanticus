from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ada.alarms.core import AlarmStatus
from ada.processes.alarm_runtime.publication.output_resolved import (
    AlarmResolvedCurrentPublisher,
    EngineResolvedCurrentPublicationError,
    build_resolved_current_document,
)
from atlanticus.state import AtomicJsonStore


class _Context:
    def __init__(self):
        self.depth = 0

    def assert_lease_current(self):
        assert self.depth == 0

    @contextmanager
    def fenced_mutation(self):
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1


class _Reference:
    source_key = 'alarm-configuration'

    def as_document(self):
        return {
            'source_key': self.source_key,
            'result_id': 'ready-result',
            'manifest_sha256': 'a' * 64,
            'resolution_key': {
                'alarm_configuration_revision': 'R1',
                'confirmed_tool_catalog_revision': 'T1',
            },
        }


class _Position:
    def __init__(self, offset=10):
        self.offset = offset

    def as_document(self):
        return {'segment_id': '20261010T190000Z', 'byte_offset': self.offset}


class _Persistence:
    def __init__(self):
        self.effective = SimpleNamespace(target_artifact_ref=_Reference())
        self.head = SimpleNamespace(aligned=True, durable=_Position())

    def read_effective_head(self):
        return self.effective

    def read_head(self):
        return self.head


class _Identity:
    canonical_key = 'family/rule'

    def __hash__(self):
        return hash(self.canonical_key)

    def __eq__(self, other):
        return isinstance(other, _Identity)


def _result(*, at=None, managed=False, assignment=False, evidence_value=10, empty=False, disposition='PREDOMINANT'):
    at = datetime(2026, 10, 10, 19, 0, tzinfo=UTC) if at is None else at
    identity = _Identity()
    key = SimpleNamespace(alarm_configuration_revision='R1', confirmed_tool_catalog_revision='T1')
    session = SimpleNamespace(configuration=SimpleNamespace(resolution_key=key))
    evaluation = SimpleNamespace(
        alarm_identity=identity,
        status=AlarmStatus.INACTIVE if empty else AlarmStatus.ACTIVE,
        evidence_snapshot=SimpleNamespace(
            contract_key='threshold', contract_version='v1', payload={'value': evidence_value}
        ),
        error=None,
    )
    cycle = SimpleNamespace(cycle_at=at, evaluations=(evaluation,))
    management = (
        SimpleNamespace(
            effect_id='management-1',
            source_occurrence_id='occ-1',
            effective_at=at - timedelta(seconds=1),
            reappearance_due_at=at + timedelta(minutes=20),
        )
        if managed else None
    )
    occurrence = SimpleNamespace(
        occurrence_id='occ-1', episode_id='episode-1',
        started_at=datetime(2026, 10, 10, 18, 0, tzinfo=UTC),
    )
    state = SimpleNamespace(
        alarm_identity=identity,
        occurrence=None if empty else occurrence,
        management_effect=management,
        deactivation_effect=None,
        technical_hold=None,
        management_cycle=1,
        assignments=(
            (SimpleNamespace(tool_key='tool-b', assigned_at=at),)
            if assignment else ()
        ),
        pending_assignments=(),
    )
    priority = SimpleNamespace(
        disposition=SimpleNamespace(value=disposition),
        blocking_alarm_identities=(() if disposition == 'PREDOMINANT' else (SimpleNamespace(canonical_key='family/source'),)),
    )
    resolution = SimpleNamespace(alarms=(SimpleNamespace(
        alarm_identity=identity, disposition=priority.disposition,
        blocking_alarm_identities=priority.blocking_alarm_identities,
    ),))
    group = SimpleNamespace(
        priority_group='group-1',
        decision=SimpleNamespace(
            priority_resolution=resolution,
            state=SimpleNamespace(alarms=(state,)),
        ),
    )
    lifecycle = SimpleNamespace(groups=(group,))
    return SimpleNamespace(session=session, cycle=cycle, lifecycle=lifecycle)


def _read(tmp_path):
    return AtomicJsonStore(root_path=tmp_path).read('current/latest.json')


def test_no_completed_cycle_is_skip_and_does_not_create_files(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    assert not publisher.publish(
        context=_Context(), persistence=_Persistence(),
        result=SimpleNamespace(cycle=None, lifecycle=None),
    )
    assert not list(tmp_path.rglob('*.json'))


def test_same_operational_state_is_skip_even_after_clock_and_cursor_advance(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    storage = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=storage, result=first)
    initial = _read(tmp_path)
    storage.head = SimpleNamespace(aligned=True, durable=_Position(30))
    later = _result(at=first.cycle.cycle_at + timedelta(seconds=1))
    assert not publisher.publish(context=_Context(), persistence=storage, result=later)
    assert _read(tmp_path) == initial


def test_management_and_reappearance_publish_without_new_physical_evidence(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    later = first.cycle.cycle_at + timedelta(seconds=1)
    assert publisher.publish(
        context=_Context(), persistence=persistence, result=_result(at=later, managed=True)
    )
    managed = _read(tmp_path)['state']['alarms'][0]
    assert managed['evaluation']['evidence']['payload'] == {'value': 10}
    assert managed['priority']['disposition'] == 'PREDOMINANT'
    assert managed['directly_managed'] is True
    assert publisher.publish(
        context=_Context(), persistence=persistence,
        result=_result(at=later + timedelta(seconds=1), managed=False),
    )
    assert _read(tmp_path)['state']['alarms'][0]['directly_managed'] is False


def test_routing_transition_publishes_even_if_evidence_is_identical(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    assert publisher.publish(
        context=_Context(), persistence=persistence,
        result=_result(at=first.cycle.cycle_at + timedelta(seconds=1), assignment=True),
    )
    assert _read(tmp_path)['state']['alarms'][0]['assignments'][0]['tool_key'] == 'tool-b'


def test_last_alarm_closes_and_empty_state_is_published_only_once(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    at = first.cycle.cycle_at + timedelta(seconds=1)
    assert publisher.publish(
        context=_Context(), persistence=persistence, result=_result(at=at, empty=True)
    )
    assert _read(tmp_path)['state']['alarms'] == []
    assert not publisher.publish(
        context=_Context(), persistence=persistence,
        result=_result(at=at + timedelta(seconds=1), empty=True),
    )


def test_different_evidence_is_meaningful_and_creates_one_replacement(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    at = first.cycle.cycle_at + timedelta(seconds=1)
    assert publisher.publish(
        context=_Context(), persistence=persistence,
        result=_result(at=at, evidence_value=11),
    )
    assert _read(tmp_path)['state']['alarms'][0]['evaluation']['evidence']['payload'] == {'value': 11}


def test_corrupt_existing_document_must_not_be_replaced(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    store = AtomicJsonStore(root_path=tmp_path)
    corrupted = _read(tmp_path)
    corrupted['state']['alarms'] = []
    store.replace('current/latest.json', corrupted)
    with pytest.raises(EngineResolvedCurrentPublicationError, match='checksum'):
        publisher.publish(
            context=_Context(), persistence=persistence,
            result=_result(at=first.cycle.cycle_at + timedelta(seconds=1)),
        )


def test_effective_mismatch_is_rejected_before_publication(tmp_path):
    wrong = _Reference().as_document()
    wrong['resolution_key']['alarm_configuration_revision'] = 'R2'
    with pytest.raises(EngineResolvedCurrentPublicationError, match='EFFECTIVE'):
        build_resolved_current_document(
            result=_result(), artifact_ref=wrong, journal_position={'segment_id': 'x'}
        )
    assert not list(tmp_path.iterdir())


def test_priority_rotation_is_published_with_identical_physical_evidence(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    assert publisher.publish(
        context=_Context(), persistence=persistence,
        result=_result(
            at=first.cycle.cycle_at + timedelta(seconds=1),
            disposition='CASCADE_SUPPRESSED',
        ),
    )
    assert _read(tmp_path)['state']['alarms'][0]['priority']['disposition'] == 'CASCADE_SUPPRESSED'


def test_unaligned_durable_head_prevents_operational_publication(tmp_path):
    persistence = _Persistence()
    persistence.head = SimpleNamespace(aligned=False, durable=_Position())
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    with pytest.raises(EngineResolvedCurrentPublicationError, match='durable EFFECTIVE'):
        publisher.publish(context=_Context(), persistence=persistence, result=_result())
    assert not list(tmp_path.rglob('*.json'))


def test_clock_rollback_cannot_overwrite_last_valid_state(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    first = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=first)
    unchanged = _read(tmp_path)
    with pytest.raises(EngineResolvedCurrentPublicationError, match='backward'):
        publisher.publish(
            context=_Context(), persistence=persistence,
            result=_result(at=first.cycle.cycle_at - timedelta(seconds=1), assignment=True),
        )
    assert _read(tmp_path) == unchanged
