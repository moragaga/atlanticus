from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ada.alarms.core import AlarmStatus, EvaluationContext
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.diagnostics import emit_evaluator_contract_diagnostics
from ada.processes.alarm_runtime.session import (
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)

from .support import engine_configuration, evaluator


def _configuration_with_two_alarms() -> EngineAlarmConfiguration:
    original = engine_configuration()
    first = original.planned_alarms[0]
    second_identity = AlarmIdentity('another', 'risk')
    second = replace(first, identity=second_identity, evaluator_key='not-yet-deployed', priority_order=2)
    return EngineAlarmConfiguration(
        resolution_key=original.resolution_key,
        defined_alarm_identities=(first.identity, second.identity),
        planned_alarms=(first, second),
        parameters_by_alarm=original.parameters_by_alarm,
    )


def test_partial_registry_evaluates_existing_alarm_and_errors_missing_one() -> None:
    configuration = _configuration_with_two_alarms()
    session = build_alarm_execution_session(
        configuration=configuration,
        evaluator_registry=AlarmEvaluatorRegistry((
            AlarmEvaluatorContract('mill', 'threshold', evaluator),
        )),
    )
    assert len(session.entries) == 2
    assert session.unregistered_alarms == (session.entries[1].identity,)
    at = datetime(2026, 10, 8, 22, tzinfo=UTC)
    outcomes = [entry.evaluator(EvaluationContext(
        alarm_identity=entry.identity, now=at, parameters=entry.parameters, data=None
    )) for entry in session.entries]
    assert outcomes[0].status is AlarmStatus.INACTIVE
    assert outcomes[1].status is AlarmStatus.ERROR
    assert outcomes[1].error.error_key == 'evaluator_contract_unavailable'


def test_unreferenced_contract_reports_only_absent_active_keys() -> None:
    config = engine_configuration()
    session = build_alarm_execution_session(
        configuration=config,
        evaluator_registry=AlarmEvaluatorRegistry((
            AlarmEvaluatorContract('mill', 'threshold', evaluator),
            AlarmEvaluatorContract('mill', 'extra', evaluator),
        )),
    )
    assert session.unregistered_alarms == ()
    assert session.unreferenced_contracts == (('mill', 'extra'),)


def test_diagnostics_emit_structured_warnings_once_per_reconciliation(monkeypatch) -> None:
    from ada.processes.alarm_runtime import diagnostics

    session = build_alarm_execution_session(
        configuration=engine_configuration(evaluator_key='missing'),
        evaluator_registry=AlarmEvaluatorRegistry((
            AlarmEvaluatorContract('mill', 'threshold', evaluator),
        )),
    )
    events = []
    monkeypatch.setattr(diagnostics, 'emit_event', lambda event: events.append(event))
    emit_evaluator_contract_diagnostics(session)
    assert [event.name for event in events] == [
        'alarm.evaluator_contract_missing',
        'alarm.evaluator_configuration_missing',
    ]
    assert events[0].attributes['evaluator_key'] == 'missing'
    assert events[0].attributes['alarm_key'] == 'risk'
    assert events[1].attributes['evaluator_key'] == 'threshold'
    assert events[1].attributes['reason'] == 'no_active_planned_alarm_references_contract'
