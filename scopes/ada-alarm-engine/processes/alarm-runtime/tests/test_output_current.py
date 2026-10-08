from __future__ import annotations

import copy
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from importlib.resources import files

import pytest

from ada.alarms.core import (
    AlarmEpisode,
    AlarmOccurrence,
    AlarmRuntimeState,
    AlarmStatus,
    GroupLifecycleState,
    RuntimeEvaluationState,
    ToolAssignment,
)
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    ConfigurationAdoptionRecord,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import snapshot_group_lifecycle
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.publication import (
    AlarmDurableCurrentPublisher,
    EngineDurableCurrentPublicationError,
)
from atlanticus.state import AtomicJsonStore

_AT = datetime(2026, 10, 8, 14, tzinfo=UTC)
_GROUP = 'mp10_temperature'
_IDENTITY = AlarmIdentity('mp10', 'high_temperature')


class _Context:
    def assert_lease_current(self):
        return None

    def fenced_mutation(self):
        return nullcontext()


def _stamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def _artifact():
    return AlarmArtifactRefSnapshot(
        source_key='alarm-configuration',
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='b' * 64,
        alarm_configuration_revision='ALARMS-MP10-DEMO',
        confirmed_tool_catalog_revision='TOOLS-MP10-DEMO',
    )


def _init(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    persistence.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    persistence.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id='adoption-mp10',
            previous_artifact_ref=None,
            target_artifact_ref=_artifact(),
            effective_at=_stamp(_AT),
            committed_at=_stamp(_AT),
        ),
        assert_authority=lambda: None,
        fenced_mutation=nullcontext,
    )
    return persistence


def _commit(persistence, *, offset: int, opened: bool):
    at = _AT + timedelta(minutes=offset)
    commit_id = f'MP10-C{offset}'
    previous = None if offset == 1 else 'MP10-C1'
    if opened:
        occurrence = AlarmOccurrence(
            occurrence_id='occ-mp10-1',
            alarm_identity=_IDENTITY,
            episode_id='episode-mp10-1',
            started_at=at,
            alarm_configuration_revision='ALARMS-MP10-DEMO',
            tool_registry_revision='TOOLS-MP10-DEMO',
        )
        state = GroupLifecycleState(
            priority_group=_GROUP,
            episode=AlarmEpisode('episode-mp10-1', _GROUP, at),
            alarms=(
                AlarmRuntimeState(
                    alarm_identity=_IDENTITY,
                    occurrence=occurrence,
                    last_evaluation=RuntimeEvaluationState(AlarmStatus.ACTIVE, at),
                    management_cycle=1,
                    assignments=(ToolAssignment('mp10', at),),
                ),
            ),
        )
    else:
        state = GroupLifecycleState(priority_group=_GROUP)
    snapshot = snapshot_group_lifecycle(
        state,
        commit_id=commit_id,
        alarm_configuration_revision='ALARMS-MP10-DEMO',
        tool_registry_revision='TOOLS-MP10-DEMO',
        technical_incidents=(),
    )
    record = EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id=commit_id,
            cycle_id=f'MP10-CYCLE-{offset}',
            priority_group=_GROUP,
            previous_commit_id=previous,
            evaluated_at=_stamp(at),
            committed_at=_stamp(at),
            alarm_configuration_revision='ALARMS-MP10-DEMO',
            tool_registry_revision='TOOLS-MP10-DEMO',
            runtime_artifact_version='ada-alarm-runtime-process/1.0.0',
            affected_alarms=(_IDENTITY.canonical_key,),
        ),
        snapshot_after=snapshot,
        records={
            'journey_events': [
                {'event_key': 'occurrence_started' if opened else 'occurrence_closed'}
            ]
        },
    )
    persistence.commit_batch(
        (record,), assert_authority=lambda: None, fenced_mutation=nullcontext
    )
    return record


def _publisher(tmp_path):
    return AlarmDurableCurrentPublisher(
        root=tmp_path / 'output', source_key='alarm-configuration'
    )


def _read(tmp_path):
    return AtomicJsonStore(root_path=tmp_path / 'output').read('current/durable-latest.json')


def test_missing_effective_is_not_confused_with_empty_current(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    persistence.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    with pytest.raises(EngineDurableCurrentPublicationError, match='EFFECTIVE'):
        _publisher(tmp_path).publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) is None


def test_effective_with_no_committed_groups_is_a_valid_empty_current(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    assert publisher.publish(context=_Context(), persistence=persistence)
    output = _read(tmp_path)
    assert output['state']['groups'] == []
    assert output['artifact_ref'] == _artifact().as_document()
    assert output['journal_position'] == persistence.read_head().durable.as_document()
    assert not publisher.publish(context=_Context(), persistence=persistence)


def test_open_closed_and_recovery_are_published_only_from_durable_state(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    first = _commit(persistence, offset=1, opened=True)
    assert publisher.publish(context=_Context(), persistence=persistence)
    opened = _read(tmp_path)
    state = opened['state']['groups'][0]
    assert state['snapshot_schema_version'] == 'group-runtime-snapshot.v3'
    assert state['alarms']['mp10/high_temperature']['occurrence']['occurrence_id'] == 'occ-mp10-1'
    assert state['last_commit_id'] == first.commit.commit_id
    assert (
        state['alarms']['mp10/high_temperature']['occurrence']['last_evaluation']['evaluated_at']
        == _stamp(_AT + timedelta(minutes=1))
    )
    before_position = opened['journal_position']
    assert not publisher.publish(context=_Context(), persistence=persistence)
    restarted = AlarmPersistence(application_root=tmp_path / 'runtime')
    restarted.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    assert not publisher.publish(context=_Context(), persistence=restarted)
    second = _commit(restarted, offset=3, opened=False)
    assert publisher.publish(context=_Context(), persistence=restarted)
    closed = _read(tmp_path)
    assert closed['journal_position'] != before_position
    assert closed['state']['groups'][0]['last_commit_id'] == second.commit.commit_id
    assert closed['state']['groups'][0]['alarms'] == {}
    assert closed['state']['groups'][0]['episode'] is None
    assert closed['sha256'] != opened['sha256']
    assert not publisher.publish(context=_Context(), persistence=restarted)


def test_corrupt_existing_document_is_not_overwritten(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    assert publisher.publish(context=_Context(), persistence=persistence)
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    corrupt = _read(tmp_path)
    corrupt['state']['groups'] = [{'unexpected': True}]
    store.replace('current/durable-latest.json', corrupt)
    with pytest.raises(EngineDurableCurrentPublicationError, match='integrity'):
        publisher.publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) == corrupt


def test_earlier_position_cannot_replace_later_publication(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    old_position = persistence.read_head().durable.as_document()
    _commit(persistence, offset=1, opened=True)
    publisher.publish(context=_Context(), persistence=persistence)
    latest = _read(tmp_path)
    stale = copy.deepcopy(latest)
    stale['journal_position'] = old_position
    from ada.processes.alarm_runtime.publication.output_current import _digest

    stale['sha256'] = _digest({key: value for key, value in stale.items() if key != 'sha256'})
    AtomicJsonStore(root_path=tmp_path / 'output').replace('current/durable-latest.json', stale)
    assert publisher.publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) == latest


def test_conflicting_payload_at_same_durable_position_is_rejected(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    assert publisher.publish(context=_Context(), persistence=persistence)
    other = _read(tmp_path)
    other['state']['groups'] = [{
        'snapshot_schema_version': 'group-runtime-snapshot.v3',
        'priority_group': 'different_group',
        'last_commit_id': 'C1',
        'state_basis': {
            'alarm_configuration_revision': 'ALARMS-MP10-DEMO',
            'tool_registry_revision': 'TOOLS-MP10-DEMO',
        },
        'episode': None,
        'alarms': {},
        'technical_incidents': {},
    }]
    from ada.processes.alarm_runtime.publication.output_current import _digest

    other['sha256'] = _digest({key: value for key, value in other.items() if key != 'sha256'})
    store = AtomicJsonStore(root_path=tmp_path / 'output')
    store.replace('current/durable-latest.json', other)
    with pytest.raises(EngineDurableCurrentPublicationError, match='Conflicting'):
        publisher.publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) == other


def test_legacy_v1_snapshot_blocks_current_without_replacing_last_good(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    assert publisher.publish(context=_Context(), persistence=persistence)
    good = _read(tmp_path)

    legacy = GroupRuntimeSnapshot({
        'snapshot_schema_version': 'group-runtime-snapshot.v1',
        'priority_group': _GROUP,
        'last_commit_id': 'MP10-LEGACY-C1',
        'alarms': {},
    })
    record = EngineCommitRecord.create(
        commit=EngineCommitMetadata(
            commit_id='MP10-LEGACY-C1',
            cycle_id='MP10-LEGACY-CYCLE-1',
            priority_group=_GROUP,
            previous_commit_id=None,
            evaluated_at=_stamp(_AT + timedelta(minutes=1)),
            committed_at=_stamp(_AT + timedelta(minutes=1)),
            alarm_configuration_revision='ALARMS-MP10-DEMO',
            tool_registry_revision='TOOLS-MP10-DEMO',
            runtime_artifact_version='ada-alarm-runtime-process/1.0.0',
            affected_alarms=(_IDENTITY.canonical_key,),
        ),
        snapshot_after=legacy,
        records={'journey_events': [{'event_key': 'legacy_commit'}]},
    )
    persistence.commit_batch(
        (record,), assert_authority=lambda: None, fenced_mutation=nullcontext
    )
    assert persistence.read_effective_head() is not None
    with pytest.raises(EngineDurableCurrentPublicationError, match='v3'):
        publisher.publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) == good


def test_corrupted_snapshot_set_is_rejected_by_persistence_before_current(
    tmp_path, monkeypatch
):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    assert publisher.publish(context=_Context(), persistence=persistence)
    good = _read(tmp_path)

    unexpected = GroupRuntimeSnapshot({
        'snapshot_schema_version': 'group-runtime-snapshot.v1',
        'priority_group': 'older',
        'last_commit_id': 'OLDER-COMMIT',
        'alarms': {},
    })
    monkeypatch.setattr(persistence, 'list_snapshots', lambda: (unexpected,))
    with pytest.raises(AlarmPersistenceCorruptionError, match='snapshots do not match'):
        publisher.publish(context=_Context(), persistence=persistence)
    assert _read(tmp_path) == good


def test_v1_schema_declares_committed_groups_and_position():
    schema = json.loads(
        files('ada.contracts.alarms')
        .joinpath('schemas/engine_durable_current_state.v1.schema.json')
        .read_text(encoding='utf-8')
    )
    assert schema['properties']['schema_version']['const'] == 1
    assert schema['properties']['journal_position']['$ref'] == '#/$defs/journal_position'
    assert (
        schema['$defs']['group_snapshot']['properties']['snapshot_schema_version']['const']
        == 'group-runtime-snapshot.v3'
    )
