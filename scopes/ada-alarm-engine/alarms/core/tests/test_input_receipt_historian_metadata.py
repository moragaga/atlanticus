from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.alarms.core import (
    DeactivationDecisionKind,
    DeactivationDecisionOutcome,
    InputKind,
    ManagementActionOutcome,
)
from ada.alarms.core.commit import InputReceipt, _build_receipts
from ada.contracts.alarms import AlarmIdentity

NOW = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)
IDENTITY = AlarmIdentity(family_key='mill', alarm_key='high-pressure')


def _decision(*, kind, outcome):
    request = SimpleNamespace(
        request_id='req-42',
        alarm_identity=IDENTITY,
        source_occurrence_id='occ-1',
    )
    decision = SimpleNamespace(
        decision_id='dec-42',
        request_id=request.request_id,
        kind=kind,
        actor_key='supervisor-1',
        decided_at=NOW,
    )
    return SimpleNamespace(
        outcome=outcome,
        decision=decision,
        deactivation_request=request,
    )


def _receipts(*, actions=(), requests=(), decisions=()):
    return _build_receipts(
        SimpleNamespace(
            management_action_results=actions,
            deactivation_request_results=requests,
            deactivation_decision_results=decisions,
        ),
        commit_id='commit-123',
        committed_at=NOW,
    )


def test_management_receipt_keeps_explicit_actor_and_input_identity():
    action = SimpleNamespace(
        input_id='manage-7',
        alarm_identity=IDENTITY,
        source_occurrence_id='occ-1',
        tool_key='tool-a',
        actor_key='operator-7',
        source_created_at=NOW,
    )
    result = SimpleNamespace(action=action, outcome=ManagementActionOutcome.EFFECTIVE)
    (receipt,) = _receipts(actions=(result,))
    assert receipt.as_document() == {
        'input_id': 'manage-7',
        'input_kind': InputKind.MANAGEMENT.value,
        'commit_id': 'commit-123',
        'applied_at': '2026-10-10T10:00:00Z',
        'outcome': ManagementActionOutcome.EFFECTIVE.value,
        'alarm_key': 'mill/high-pressure',
        'occurrence_id': 'occ-1',
        'tool_key': 'tool-a',
        'actor_key': 'operator-7',
        'event_at': '2026-10-10T10:00:00Z',
    }


@pytest.mark.parametrize(
    ('kind', 'outcome'),
    [
        (DeactivationDecisionKind.REJECTED, DeactivationDecisionOutcome.REJECTED),
        (DeactivationDecisionKind.APPROVED, DeactivationDecisionOutcome.APPLIED),
    ],
)
def test_deactivation_receipt_preserves_actor_request_and_decision(kind, outcome):
    (receipt,) = _receipts(decisions=(_decision(kind=kind, outcome=outcome),))
    document = receipt.as_document()
    assert document['input_kind'] == 'DEACTIVATION_DECISION'
    assert document['input_id'] == 'dec-42'
    assert document['request_id'] == 'req-42'
    assert document['actor_key'] == 'supervisor-1'
    assert document['decision_kind'] == kind.value
    assert document['outcome'] == outcome.value
    assert document['event_at'] == '2026-10-10T10:00:00Z'
    assert document['occurrence_id'] == 'occ-1'
    assert document['alarm_key'] == 'mill/high-pressure'


def test_legacy_receipt_encoding_remains_unchanged_without_optional_fields():
    receipt = InputReceipt(
        input_id='old-1',
        input_kind=InputKind.MANAGEMENT,
        commit_id='commit-123',
        applied_at=NOW,
        outcome='EFFECTIVE',
    )
    assert set(receipt.as_document()) == {
        'input_id', 'input_kind', 'commit_id', 'applied_at', 'outcome'
    }


def test_pending_deactivation_decision_does_not_create_application_receipt():
    result = _decision(
        kind=DeactivationDecisionKind.APPROVED,
        outcome=DeactivationDecisionOutcome.PENDING_DEPENDENCY,
    )
    assert _receipts(decisions=(result,)) == ()


def test_deactivation_request_receipt_links_request_and_original_actor():
    action = SimpleNamespace(
        input_id='deactivate-3',
        alarm_identity=IDENTITY,
        source_occurrence_id='occ-1',
        tool_key='tool-b',
        actor_key='operator-3',
        source_created_at=NOW,
    )
    outcome = SimpleNamespace(value='PENDING_APPROVAL')
    request = SimpleNamespace(request_id='req-3')
    result = SimpleNamespace(
        action=action,
        outcome=ManagementActionOutcome.EFFECTIVE,
    )
    deactivation_result = SimpleNamespace(
        action=action,
        outcome=outcome,
        deactivation_request=request,
    )
    (receipt,) = _receipts(actions=(result,), requests=(deactivation_result,))
    record = receipt.as_document()
    assert record['input_kind'] == 'DEACTIVATION_REQUEST'
    assert record['request_id'] == 'req-3'
    assert record['actor_key'] == 'operator-3'
    assert record['tool_key'] == 'tool-b'
    assert record['alarm_key'] == 'mill/high-pressure'
