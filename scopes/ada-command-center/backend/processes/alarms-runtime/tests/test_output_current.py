from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ada_command_center.alarms.persistence import AlarmArtifactRefSnapshot
from ada_command_center.processes.alarms_runtime.publication.output_current import (
    AlarmCurrentStatePublisher,
    EngineCurrentPublicationError,
)
from atlanticus.state import AtomicJsonStore

_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Identity:
    canonical_key: str


def _pin():
    return AlarmArtifactRefSnapshot(
        source_key='alarms',
        result_id='alarm-materialization-' + '0' * 64,
        manifest_sha256='1' * 64,
        alarm_configuration_revision='R1',
        confirmed_tool_catalog_revision='C1',
    )


class _Context:
    def assert_lease_current(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        yield


def _result(*, as_of=_AT, active=True):
    identity = _Identity('mina/a')
    state = SimpleNamespace(
        alarm_identity=identity,
        occurrence=(
            SimpleNamespace(occurrence_id='occ-1', episode_id='ep-1', started_at=_AT)
            if active
            else None
        ),
        management_cycle=0,
        technical_hold=None,
        management_effect=None,
        deactivation_effect=None,
        assignments=(SimpleNamespace(tool_key='mine', assigned_at=_AT),),
        pending_assignments=(),
    )
    priority = SimpleNamespace(
        alarm_identity=identity,
        disposition=SimpleNamespace(value='PREDOMINANT'),
        blocking_alarm_identities=(),
    )
    group = SimpleNamespace(
        decision=SimpleNamespace(
            state=SimpleNamespace(alarms=(state,)),
            priority_resolution=SimpleNamespace(alarms=(priority,)),
        )
    )
    evaluation = SimpleNamespace(
        alarm_identity=identity,
        status=SimpleNamespace(value='ACTIVE'),
        evaluated_at=as_of,
        evidence_snapshot=SimpleNamespace(
            contract_key='temperature', contract_version='v1', payload={'observed_value': 82.0}
        ),
        error=None,
    )
    return SimpleNamespace(
        iteration=SimpleNamespace(as_of=as_of),
        groups=(group,),
        evaluations=(evaluation,),
    )


def _inputs():
    return SimpleNamespace(pending_deactivation_requests=())


def test_current_contains_actual_open_occurrence_and_current_evidence(tmp_path):
    publisher = AlarmCurrentStatePublisher(root=tmp_path, source_key='alarms')
    assert publisher.publish(context=_Context(), result=_result(), pin=_pin(), inputs=_inputs())
    value = AtomicJsonStore(root_path=tmp_path).read('current/latest.json')
    assert value['state']['resolution_key'] == _pin().as_document()['resolution_key']
    assert value['state']['alarms'][0]['identity'] == 'mina/a'
    assert (
        value['state']['alarms'][0]['evaluation']['evidence']['payload']['observed_value'] == 82.0
    )
    assert value['state']['alarms'][0]['priority']['disposition'] == 'PREDOMINANT'
    assert not publisher.publish(context=_Context(), result=_result(), pin=_pin(), inputs=_inputs())


def test_empty_current_is_real_not_missing_and_cannot_regress(tmp_path):
    publisher = AlarmCurrentStatePublisher(root=tmp_path, source_key='alarms')
    late = _AT + timedelta(seconds=10)
    assert publisher.publish(
        context=_Context(), result=_result(as_of=late, active=False), pin=_pin(), inputs=_inputs()
    )
    value = AtomicJsonStore(root_path=tmp_path).read('current/latest.json')
    assert value['state']['alarms'] == []
    with pytest.raises(EngineCurrentPublicationError, match='backward'):
        publisher.publish(context=_Context(), result=_result(), pin=_pin(), inputs=_inputs())


def test_tampered_current_fails_closed(tmp_path):
    publisher = AlarmCurrentStatePublisher(root=tmp_path, source_key='alarms')
    publisher.publish(context=_Context(), result=_result(), pin=_pin(), inputs=_inputs())
    store = AtomicJsonStore(root_path=tmp_path)
    document = store.read('current/latest.json')
    document['state']['alarms'] = []
    store.replace('current/latest.json', document)
    with pytest.raises(EngineCurrentPublicationError, match='integrity'):
        publisher.publish(
            context=_Context(),
            result=_result(as_of=_AT + timedelta(seconds=10)),
            pin=_pin(),
            inputs=_inputs(),
        )
