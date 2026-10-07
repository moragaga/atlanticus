from datetime import UTC, datetime, timedelta

import pytest

from ada.alarms.core import (
    DeactivationDecision,
    DeactivationDecisionKind,
    DeactivationRequest,
    ManagementAction,
)
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime import AlarmOperationalInputs, AlarmPendingDeactivationRequest

AT = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity('mill', 'risk')


def _pending() -> AlarmPendingDeactivationRequest:
    return AlarmPendingDeactivationRequest(
        request=DeactivationRequest(
            request_id='request-1',
            alarm_identity=IDENTITY,
            source_management_input_id='management-1',
            source_occurrence_id='occurrence-1',
            requested_at=AT,
            effective_until=AT + timedelta(hours=1),
            approval_required=True,
        ),
        priority_group='mill_feed',
    )


def test_operational_inputs_accept_decision_for_pending_request() -> None:
    pending = _pending()
    decision = DeactivationDecision(
        decision_id='decision-1',
        request_id=pending.request_id,
        kind=DeactivationDecisionKind.APPROVED,
        decided_at=AT + timedelta(minutes=1),
        actor_key='supervisor',
    )

    inputs = AlarmOperationalInputs(
        pending_deactivation_requests=(pending,),
        deactivation_decisions=(decision,),
    )

    assert inputs.pending_deactivation_requests == (pending,)
    assert inputs.deactivation_decisions == (decision,)


def test_operational_inputs_reject_decision_without_pending_request() -> None:
    decision = DeactivationDecision(
        decision_id='decision-1',
        request_id='missing',
        kind=DeactivationDecisionKind.REJECTED,
        decided_at=AT,
        actor_key='supervisor',
    )

    with pytest.raises(ValueError, match='pending deactivation request'):
        AlarmOperationalInputs(deactivation_decisions=(decision,))


def test_operational_inputs_reject_duplicate_management_input_id() -> None:
    action = ManagementAction(
        input_id='management-1',
        alarm_identity=IDENTITY,
        source_occurrence_id='occurrence-1',
        tool_key='tool_a',
        actor_key='operator',
        source_created_at=AT,
    )

    with pytest.raises(ValueError, match='duplicate input_id'):
        AlarmOperationalInputs(management_actions=(action, action))
