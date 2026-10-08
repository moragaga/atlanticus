from datetime import UTC, datetime, timedelta

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    TechnicalIncident,
    TechnicalIncidentChangeKind,
)
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycleResult,
    AlarmLifecycleCycle,
    build_alarm_execution_session,
)

from .support import engine_configuration, registry

AT = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def _session():
    return build_alarm_execution_session(
        configuration=engine_configuration(),
        evaluator_registry=registry(),
    )


def _cycle(session, *, at, status=AlarmStatus.ERROR, error_key='missing_input'):
    if status is AlarmStatus.ERROR:
        evaluations = (
            AlarmEvaluation(
                alarm_identity=session.entries[0].identity,
                status=status,
                evaluated_at=at,
                error=EvaluationError(
                    origin=EvaluationErrorOrigin.QUALITY,
                    error_key=error_key,
                    message='Insufficient input quality',
                ),
            ),
        )
    else:
        evaluations = (
            AlarmEvaluation(
                alarm_identity=session.entries[0].identity,
                status=status,
                evaluated_at=at,
                evidence_snapshot=EvidenceSnapshot(
                    contract_key='test', contract_version='1', payload={}
                ),
            ),
        )
    return AlarmEvaluationCycleResult(cycle_at=at, evaluations=evaluations)


def test_lifecycle_pins_initial_error_without_physical_occurrence_and_deduplicates() -> None:
    session = _session()
    lifecycle = AlarmLifecycleCycle()
    first = lifecycle.run(previous=None, session=session, cycle=_cycle(session, at=AT))
    assert len(first.technical_incident_changes) == 1
    assert first.technical_incident_changes[0].kind is TechnicalIncidentChangeKind.STARTED
    assert first.state.groups == ()
    assert len(first.state.technical_incidents) == 1
    next_at = AT + timedelta(seconds=3)
    second = lifecycle.run(previous=first.state, session=session, cycle=_cycle(session, at=next_at))
    assert second.technical_incident_changes == ()
    assert second.state.technical_incidents == first.state.technical_incidents


def test_lifecycle_keeps_one_incident_across_error_change_and_resolves() -> None:
    session = _session()
    lifecycle = AlarmLifecycleCycle()
    first = lifecycle.run(previous=None, session=session, cycle=_cycle(session, at=AT))
    changed_at = AT + timedelta(seconds=3)
    changed = lifecycle.run(
        previous=first.state,
        session=session,
        cycle=_cycle(session, at=changed_at, error_key='timeout'),
    )
    assert len(changed.technical_incident_changes) == 1
    assert changed.technical_incident_changes[0].kind is TechnicalIncidentChangeKind.CHANGED
    assert (
        changed.state.technical_incidents[0].incident_id
        == first.state.technical_incidents[0].incident_id
    )
    resolved = lifecycle.run(
        previous=changed.state,
        session=session,
        cycle=_cycle(session, at=changed_at + timedelta(seconds=3), status=AlarmStatus.ACTIVE),
    )
    assert len(resolved.technical_incident_changes) == 1
    assert resolved.technical_incident_changes[0].kind is TechnicalIncidentChangeKind.RESOLVED
    assert resolved.state.technical_incidents == ()
    assert len(resolved.state.groups) == 1
    assert resolved.state.groups[0].episode is not None


def test_lifecycle_restored_incident_does_not_emit_second_start() -> None:
    session = _session()
    first = AlarmLifecycleCycle().run(previous=None, session=session, cycle=_cycle(session, at=AT))
    saved = first.state.technical_incidents[0].as_document()
    restored = TechnicalIncident.from_document(saved)
    previous = type(first.state)(
        configuration=first.state.configuration,
        groups=first.state.groups,
        technical_incidents=(restored,),
    )
    next_at = AT + timedelta(seconds=3)
    next_result = AlarmLifecycleCycle().run(
        previous=previous, session=session, cycle=_cycle(session, at=next_at)
    )
    assert next_result.technical_incident_changes == ()
    assert next_result.state.technical_incidents == (restored,)
