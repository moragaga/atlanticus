from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

from ada.alarms.core import AlarmStatus
from ada.processes.alarm_runtime.publication.output_resolved import (
    AlarmResolvedCurrentPublisher,
    build_resolved_current_document,
)

from .test_output_resolved import _Context, _Persistence, _read, _result


class _LowerIdentity:
    canonical_key = 'family/lower'

    def __hash__(self):
        return hash(self.canonical_key)

    def __eq__(self, other):
        return isinstance(other, _LowerIdentity)


def _error(result):
    evaluation = result.cycle.evaluations[0]
    evaluation.status = AlarmStatus.ERROR
    evaluation.evidence_snapshot = None
    evaluation.error = SimpleNamespace(
        origin=SimpleNamespace(value='QUALITY'),
        error_key='insufficient_samples',
        message='Input quality unavailable',
        affected_inputs=(),
    )
    return result


def test_initial_error_has_no_live_alarm(tmp_path):
    result = _error(_result(empty=True))
    output = build_resolved_current_document(
        result=result,
        artifact_ref=_Persistence().effective.target_artifact_ref.as_document(),
        journal_position=_Persistence().head.durable.as_document(),
    )
    assert output['state']['alarms'] == []


def test_open_error_hold_disappears_without_closing_occurrence_or_changing_cursor(tmp_path):
    publisher = AlarmResolvedCurrentPublisher(root=tmp_path, source_key='alarm-configuration')
    persistence = _Persistence()
    initial = _result()
    assert publisher.publish(context=_Context(), persistence=persistence, result=initial)
    source_position = _read(tmp_path)['journal_position']
    failed_at = initial.cycle.cycle_at + timedelta(seconds=1)
    failed = _error(_result(at=failed_at))
    retained = failed.lifecycle.groups[0].decision.state.alarms[0]
    retained.technical_hold = SimpleNamespace(
        started_at=failed_at, due_at=failed_at + timedelta(minutes=5)
    )
    assert retained.occurrence.occurrence_id == 'occ-1'
    assert publisher.publish(context=_Context(), persistence=persistence, result=failed)
    hidden = _read(tmp_path)
    assert hidden['state']['alarms'] == []
    assert hidden['journal_position'] == source_position
    assert not publisher.publish(context=_Context(), persistence=persistence, result=failed)
    recovered = _result(at=failed_at + timedelta(seconds=1))
    assert publisher.publish(context=_Context(), persistence=persistence, result=recovered)
    restored = _read(tmp_path)
    assert restored['state']['alarms'][0]['occurrence_id'] == 'occ-1'
    assert restored['journal_position'] == source_position


def test_error_on_predominant_keeps_lower_rule_eclipsed_in_source():
    failed = _error(_result())
    top = failed.lifecycle.groups[0].decision.state.alarms[0]
    top.technical_hold = SimpleNamespace(
        started_at=failed.cycle.cycle_at,
        due_at=failed.cycle.cycle_at + timedelta(minutes=5),
    )
    lower_identity = _LowerIdentity()
    lower_evaluation = deepcopy(failed.cycle.evaluations[0])
    lower_evaluation.alarm_identity = lower_identity
    lower_evaluation.status = AlarmStatus.ACTIVE
    lower_evaluation.error = None
    lower = deepcopy(top)
    lower.alarm_identity = lower_identity
    lower.occurrence.occurrence_id = 'occ-lower'
    lower.technical_hold = None
    lower_priority = SimpleNamespace(
        alarm_identity=lower_identity,
        disposition=SimpleNamespace(value='ECLIPSED'),
        blocking_alarm_identities=(top.alarm_identity,),
    )
    group = failed.lifecycle.groups[0]
    group.decision.state.alarms = (top, lower)
    group.decision.priority_resolution.alarms += (lower_priority,)
    failed.cycle.evaluations += (lower_evaluation,)
    document = build_resolved_current_document(
        result=failed,
        artifact_ref=_Persistence().effective.target_artifact_ref.as_document(),
        journal_position=_Persistence().head.durable.as_document(),
    )
    assert [item['identity'] for item in document['state']['alarms']] == ['family/lower']
    assert document['state']['alarms'][0]['priority']['disposition'] == 'ECLIPSED'
    assert document['state']['alarms'][0]['priority']['blockers'] == ['family/rule']
