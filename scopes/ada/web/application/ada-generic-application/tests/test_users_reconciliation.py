from __future__ import annotations

from dataclasses import replace

import pytest

from ada.web.application.generic.users_reconciliation import AdaUsersReconciliationWorkflow
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    UserIdentity,
)
from atlanticus.web.users.reconstruction import UsersReconstructionConflictError
from ada.web.application.configuration_manager.local_runtime import InProcessUsersRuntimeStore


def _user(subject: str = 'alice', *, access_keys: tuple[str, ...] = ()) -> RuntimeUser:
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer', subject_id=subject, display_name=subject,
    )
    return RuntimeUser(
        identity=identity, enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE), access_keys=access_keys,
    )


class Materializer:
    def __init__(self, users):
        self.users = users

    def materialize_all(self):
        return tuple(self.users)

    def materialize_user(self, user_id):
        return next(user for user in self.users if user.user_id == user_id)


def test_integral_reconciliation_updates_access_profile_and_operational_together():
    before = _user(access_keys=('admin.manage',))
    desired = replace(
        before, profile=RuntimeProfile.from_profile(ROOT_PROFILE),
        access_keys=('reports.view',),
        operational=RuntimeOperational(
            position=RuntimeOperationalReference(id='operator', label='Operator')
        ),
    )
    runtime = InProcessUsersRuntimeStore((before,))
    workflow = AdaUsersReconciliationWorkflow(
        materializer=Materializer((desired,)), runtime=runtime
    )
    preview = workflow.inspect()
    assert preview.update_ids == (before.user_id,)
    assert workflow.apply(preview).has_changes is False
    assert runtime.list_users() == (desired,)
    assert workflow.inspect().has_changes is False


def test_missing_member_disables_and_revokes_without_deleting_runtime():
    user = _user(access_keys=('admin.manage',))
    runtime = InProcessUsersRuntimeStore((user,))
    workflow = AdaUsersReconciliationWorkflow(materializer=Materializer(()), runtime=runtime)
    preview = workflow.inspect()
    assert preview.disable_ids == (user.user_id,)
    workflow.apply(preview)
    assert runtime.list_users() == (replace(user, enabled=False, access_keys=()),)


def test_stale_preview_refused_before_writing():
    user = _user()
    desired = replace(user, enabled=False)
    materializer = Materializer((desired,))
    runtime = InProcessUsersRuntimeStore((user,))
    workflow = AdaUsersReconciliationWorkflow(materializer=materializer, runtime=runtime)
    preview = workflow.inspect()
    materializer.users = (replace(desired, profile=RuntimeProfile.from_profile(ROOT_PROFILE)),)
    with pytest.raises(UsersReconstructionConflictError, match='sources changed'):
        workflow.apply(preview)
    assert runtime.list_users() == (user,)


def test_unverified_operational_clear_is_blocked():
    before = replace(
        _user(), operational=RuntimeOperational(
            area=RuntimeOperationalReference(id='mina', label='Mina')
        ),
    )
    runtime = InProcessUsersRuntimeStore((before,))
    workflow = AdaUsersReconciliationWorkflow(
        materializer=Materializer((_user(),)), runtime=runtime
    )
    with pytest.raises(UsersReconstructionConflictError, match='cannot be cleared'):
        workflow.apply(workflow.inspect())
    assert runtime.list_users() == (before,)


def test_individual_publication_uses_full_desired_user():
    user = _user()
    desired = replace(user, access_keys=('dashboard.view',))
    runtime = InProcessUsersRuntimeStore((user,))
    workflow = AdaUsersReconciliationWorkflow(
        materializer=Materializer((desired,)), runtime=runtime
    )
    assert workflow.publish_one(user.user_id) == desired
    assert runtime.list_users() == (desired,)


def test_conditional_write_refuses_concurrent_access_update():
    user = _user(access_keys=('dashboard.view',))
    desired = replace(user, access_keys=('reports.view',))

    class RacingStore(InProcessUsersRuntimeStore):
        def upsert_user_if_current(self, item, *, expected):
            self.upsert_user(replace(user, access_keys=('critical.new', 'dashboard.view')))
            return super().upsert_user_if_current(item, expected=expected)

    runtime = RacingStore((user,))
    workflow = AdaUsersReconciliationWorkflow(
        materializer=Materializer((desired,)), runtime=runtime
    )
    with pytest.raises(UsersReconstructionConflictError, match='changed'):
        workflow.apply(workflow.inspect())
    assert runtime.list_users()[0].access_keys == ('critical.new', 'dashboard.view')


def test_partial_failure_allows_new_inspection_and_retry():
    alice, bob = _user('alice'), _user('bob')

    class InterruptedStore(InProcessUsersRuntimeStore):
        def __init__(self):
            super().__init__()
            self.writes = 0
            self.fail = True

        def upsert_user_if_current(self, user, *, expected):
            self.writes += 1
            if self.fail and self.writes == 2:
                raise RuntimeError('Simulated partial failure')
            return super().upsert_user_if_current(user, expected=expected)

    runtime = InterruptedStore()
    workflow = AdaUsersReconciliationWorkflow(
        materializer=Materializer((alice, bob)), runtime=runtime
    )
    with pytest.raises(RuntimeError, match='partial failure'):
        workflow.apply(workflow.inspect())
    assert len(runtime.list_users()) == 1
    runtime.fail = False
    remaining = workflow.inspect()
    assert len(remaining.create_ids) == 1
    assert len(remaining.update_ids) == 0
    workflow.apply(remaining)
    assert runtime.list_users() == tuple(sorted((alice, bob), key=lambda user: user.user_id))
