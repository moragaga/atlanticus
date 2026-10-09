from __future__ import annotations

from ada.processes.alarm_runtime.session import AlarmExecutionSession
from atlanticus.observability import (
    EventAudience,
    EventCategory,
    EventSeverity,
    ObservabilityEvent,
    emit_event,
)


def emit_evaluator_contract_diagnostics(session: AlarmExecutionSession) -> None:
    if not isinstance(session, AlarmExecutionSession):
        raise TypeError('session must be an AlarmExecutionSession')
    revision = session.resolution_key.alarm_configuration_revision
    for entry in session.entries:
        if entry.contract_available:
            continue
        emit_event(
            ObservabilityEvent(
                name='alarm.evaluator_contract_missing',
                category=EventCategory.DIAGNOSTIC,
                audience=EventAudience.OPERATIONS,
                severity=EventSeverity.WARNING,
                status='warning',
                message='Configured alarm evaluator contract is not deployed',
                attributes={
                    'family_key': entry.identity.family_key,
                    'alarm_key': entry.identity.alarm_key,
                    'evaluator_key': entry.planned_alarm.evaluator_key,
                    'alarm_configuration_revision': revision,
                    'reason': 'evaluator_not_registered',
                },
            )
        )
    for family_key, evaluator_key in session.unreferenced_contracts:
        emit_event(
            ObservabilityEvent(
                name='alarm.evaluator_configuration_missing',
                category=EventCategory.DIAGNOSTIC,
                audience=EventAudience.OPERATIONS,
                severity=EventSeverity.WARNING,
                status='warning',
                message='Registered evaluator has no active planned alarm',
                attributes={
                    'family_key': family_key,
                    'evaluator_key': evaluator_key,
                    'alarm_configuration_revision': revision,
                    'reason': 'no_active_planned_alarm_references_contract',
                },
            )
        )
