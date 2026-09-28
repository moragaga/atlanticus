from types import SimpleNamespace

import pytest

from atlanticus.web.users.recovery import UsersRecoveryConflictError
from atlanticus.web.users.web.projection_workflow import UsersProjectionWorkflow


class Recovery:
    def __init__(self):
        self.version = 'v1'
        self.aligned = False
        self.calls = []

    def preview_capture(self):
        return SimpleNamespace(
            content_digest='digest',
            registry_version=self.version,
            approved_users=(SimpleNamespace(user_id='user-a'),),
            candidate_user_ids=('candidate-b',),
        )

    def capture(self, **arguments):
        self.calls.append(('capture', arguments))
        return SimpleNamespace(
            snapshot_id='snapshot-b',
            content_digest='digest',
            users=(object(),),
            origin_environment='target',
        )

    def validate_replace(self, snapshot_id):
        assert snapshot_id == 'snapshot-a'
        user = SimpleNamespace(user_id='user-a', to_document=lambda: {'user_id': 'user-a'})
        snapshot = SimpleNamespace(
            snapshot_id=snapshot_id,
            content_digest='digest',
            origin_environment='origin',
            captured_at_utc='2026-09-28T00:00:00+00:00',
            users=(user,),
        )
        recovery = SimpleNamespace(
            snapshot=snapshot,
            registry_version=self.version,
            registry_state=SimpleNamespace(value='match' if self.aligned else 'conflict'),
            registry_conflict_user_ids=() if self.aligned else ('candidate-b',),
            can_restore=False,
            differences=() if self.aligned else (
                SimpleNamespace(
                    user_id='user-a',
                    kind=SimpleNamespace(value='different'),
                    fields=('enabled',),
                ),
            ),
        )
        plan = SimpleNamespace(
            create_ids=(),
            update_ids=() if self.aligned else ('user-a',),
            delete_ids=(),
            unchanged_ids=('user-a',) if self.aligned else (),
            registry_discarded_ids=() if self.aligned else ('candidate-b',),
            registry_write_required=not self.aligned,
        )
        return SimpleNamespace(
            recovery=recovery,
            can_replace=True,
            versioned_users=(SimpleNamespace(user=user, version=self.version),),
            plan=plan,
        )

    def replace_approved(self, **arguments):
        self.calls.append(('replace', arguments))
        self.aligned = True
        return self.validate_replace('snapshot-a')


def _workflow(service):
    return UsersProjectionWorkflow(
        recovery=service,
        snapshot_ids=lambda: ('snapshot-a',),
        operator_id=lambda: 'authenticated-operator',
    )


def test_capture_requires_exact_preview_and_uses_authenticated_operator():
    recovery = Recovery()
    workflow = _workflow(recovery)
    preview = workflow.preview_capture()
    assert preview['candidate_ids'] == ['candidate-b']
    recovery.version = 'v2'
    with pytest.raises(UsersRecoveryConflictError, match='changed'):
        workflow.capture(preview, 'APPROVAL-1')
    saved = workflow.capture(workflow.preview_capture(), 'APPROVAL-1')
    assert saved['snapshot_id'] == 'snapshot-b'
    assert recovery.calls[-1][1]['operator_id'] == 'authenticated-operator'


def test_replace_requires_review_and_same_inspection():
    recovery = Recovery()
    workflow = _workflow(recovery)
    inspected = workflow.inspect('snapshot-a')
    assert inspected['update_ids'] == ['user-a']
    assert inspected['discarded_candidate_ids'] == ['candidate-b']
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        workflow.apply(
            inspection=inspected, mode='replace', approval_reference='APPROVAL-1',
            maintenance_confirmed=True, revocations_reviewed=True,
            confirmed=False,
        )
    recovery.version = 'v2'
    with pytest.raises(UsersRecoveryConflictError, match='Target changed'):
        workflow.apply(
            inspection=inspected, mode='replace', approval_reference='APPROVAL-1',
            maintenance_confirmed=True, revocations_reviewed=True,
            confirmed=True,
        )
    inspected = workflow.inspect('snapshot-a')
    result = workflow.apply(
        inspection=inspected, mode='replace', approval_reference='APPROVAL-1',
        maintenance_confirmed=True, revocations_reviewed=True,
        confirmed=True,
    )
    assert result['updated'] == 1
    assert result['discarded_candidates'] == 1
    assert recovery.calls[-1][1]['operator_id'] == 'authenticated-operator'
    with pytest.raises(UsersRecoveryConflictError, match='already aligned'):
        workflow.apply(
            inspection=workflow.inspect('snapshot-a'), mode='replace',
            approval_reference='APPROVAL-1', maintenance_confirmed=True,
            revocations_reviewed=True, confirmed=True,
        )


def test_recovery_factory_is_lazy_and_resolves_once_per_action():
    events = []
    service = Recovery()

    def provide():
        events.append('resolved')
        return service

    workflow = _workflow(provide)
    assert workflow.history() == ('snapshot-a',)
    assert events == []
    assert workflow.preview_capture()['digest'] == 'digest'
    assert events == ['resolved']
    workflow.inspect('snapshot-a')
    assert events == ['resolved', 'resolved']


def test_strict_restore_requires_modal_confirmation_and_keeps_non_missing_users():
    class StrictRecovery(Recovery):
        def validate_replace(self, snapshot_id):
            value = super().validate_replace(snapshot_id)
            value.recovery.can_restore = True
            value.recovery.registry_state.value = 'match'
            value.plan.create_ids = ('missing-user',) if not self.aligned else ()
            value.plan.update_ids = ()
            value.plan.delete_ids = ()
            value.plan.registry_discarded_ids = ()
            value.plan.registry_write_required = False
            value.recovery.differences = () if self.aligned else (
                SimpleNamespace(
                    user_id='missing-user', kind=SimpleNamespace(value='missing'), fields=(),
                ),
            )
            return value

        def restore(self, **arguments):
            self.calls.append(('restore', arguments))
            self.aligned = True
            return SimpleNamespace(differences=(), registry_state=SimpleNamespace(value='match'))

    service = StrictRecovery()
    workflow = _workflow(service)
    inspection = workflow.inspect('snapshot-a')
    with pytest.raises(UsersRecoveryConflictError, match='confirmation'):
        workflow.apply(
            inspection=inspection, mode='restore', approval_reference='TICKET-1',
            maintenance_confirmed=True, revocations_reviewed=True, confirmed=False,
        )
    result = workflow.apply(
        inspection=inspection, mode='restore', approval_reference='TICKET-1',
        maintenance_confirmed=True, revocations_reviewed=True, confirmed=True,
    )
    assert result['created'] == 1
    assert result['updated'] == result['deleted'] == 0
    assert service.calls[-1][0] == 'restore'
    assert service.calls[-1][1]['operator_id'] == 'authenticated-operator'
