from dataclasses import replace

import pytest

from ada.web.application.generic.users_reconciliation import (
    AdaUsersRuntimeReconciler,
    UsersRuntimeReconciliationChangedError,
    UsersRuntimeReconciliationError,
    UsersRuntimeReconciliationIncompleteError,
)
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


def _user(subject: str, *, enabled: bool = True, access_keys: tuple[str, ...] = ()) -> RuntimeUser:
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name=subject,
    )
    return RuntimeUser(
        identity=identity,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=access_keys,
    )


class _Materializer:
    def __init__(self, users: tuple[RuntimeUser, ...]) -> None:
        self.users = users
        self.reads = 0

    def materialize_all(self) -> tuple[RuntimeUser, ...]:
        self.reads += 1
        return self.users


class _Store:
    def __init__(self, users: tuple[RuntimeUser, ...]) -> None:
        self.users = users
        self.writes = 0
        self.fail_after_partial_write = False
        self.return_incomplete = False

    def list_users(self) -> tuple[RuntimeUser, ...]:
        return self.users

    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]:
        self.writes += 1
        if self.fail_after_partial_write:
            self.users = users[:1]
            raise RuntimeError('Simulated partial write')
        if self.return_incomplete:
            return self.users
        self.users = users
        return self.users


def test_preview_reports_all_differences_without_mutating_runtime():
    current = (_user('alice', enabled=False), _user('obsolete'))
    desired = (_user('alice', access_keys=('dashboard.view',)), _user('bob'))
    store = _Store(current)
    reconcile = AdaUsersRuntimeReconciler(materializer=_Materializer(desired), store=store)

    plan = reconcile.preview()

    assert plan.creates == (desired[1].user_id,)
    assert plan.updates == (desired[0].user_id,)
    assert plan.deletes == (current[1].user_id,)
    assert plan.unchanged == ()
    assert plan.target_count == 2
    assert store.writes == 0
    assert store.users == current


def test_application_requires_same_preview_and_explicit_deletion_permission():
    current = (_user('obsolete'),)
    desired = (_user('alice'),)
    store = _Store(current)
    materializer = _Materializer(desired)
    reconcile = AdaUsersRuntimeReconciler(materializer=materializer, store=store)
    plan = reconcile.preview()

    with pytest.raises(UsersRuntimeReconciliationChangedError):
        reconcile.apply(expected_plan_id='wrong', actor='admin', allow_deletes=True)
    with pytest.raises(UsersRuntimeReconciliationError, match='deletion requires'):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='admin')
    with pytest.raises(TypeError, match='boolean'):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='admin', allow_deletes='yes')
    assert store.writes == 0

    result = reconcile.apply(expected_plan_id=plan.plan_id, actor='admin', allow_deletes=True)

    assert result.plan == plan
    assert result.actor == 'admin'
    assert result.persisted_count == 1
    assert store.users == desired
    assert store.writes == 1


def test_outdated_source_and_runtime_cancel_before_first_write():
    alice = _user('alice')
    bob = _user('bob')
    materializer = _Materializer((alice,))
    store = _Store(())
    reconcile = AdaUsersRuntimeReconciler(materializer=materializer, store=store)
    old_plan = reconcile.preview()
    materializer.users = (bob,)

    with pytest.raises(UsersRuntimeReconciliationChangedError):
        reconcile.apply(expected_plan_id=old_plan.plan_id, actor='admin')
    assert store.writes == 0

    new_plan = reconcile.preview()
    store.users = (alice,)
    with pytest.raises(UsersRuntimeReconciliationChangedError):
        reconcile.apply(expected_plan_id=new_plan.plan_id, actor='admin', allow_deletes=True)
    assert store.writes == 0


def test_no_changes_are_idempotent_and_require_no_cosmos_writes():
    user = _user('alice')
    store = _Store((user,))
    reconcile = AdaUsersRuntimeReconciler(materializer=_Materializer((user,)), store=store)

    plan = reconcile.preview()
    result = reconcile.apply(expected_plan_id=plan.plan_id, actor='admin')

    assert plan.unchanged == (user.user_id,)
    assert not plan.has_changes
    assert result.persisted_count == 1
    assert store.writes == 0


def test_partial_write_fails_without_reporting_success_and_allows_new_preview():
    desired = (_user('alice'), _user('bob'))
    store = _Store(())
    store.fail_after_partial_write = True
    reconcile = AdaUsersRuntimeReconciler(materializer=_Materializer(desired), store=store)
    plan = reconcile.preview()

    with pytest.raises(UsersRuntimeReconciliationIncompleteError, match='did not complete'):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='admin')
    ordered = tuple(sorted(desired, key=lambda user: user.user_id))
    assert store.users == ordered[:1]

    store.fail_after_partial_write = False
    recovery = reconcile.preview()
    assert recovery.creates == (ordered[1].user_id,)
    assert recovery.unchanged == (ordered[0].user_id,)
    assert recovery.plan_id != plan.plan_id
    assert reconcile.apply(expected_plan_id=recovery.plan_id, actor='admin').persisted_count == 2


def test_runtime_store_disagreement_reports_incomplete_publication():
    store = _Store(())
    store.return_incomplete = True
    reconcile = AdaUsersRuntimeReconciler(materializer=_Materializer((_user('alice'),)), store=store)
    plan = reconcile.preview()
    with pytest.raises(UsersRuntimeReconciliationIncompleteError):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='admin')


def test_invalid_actor_is_rejected_before_any_write():
    store = _Store(())
    reconcile = AdaUsersRuntimeReconciler(materializer=_Materializer((_user('alice'),)), store=store)
    plan = reconcile.preview()
    with pytest.raises(ValueError, match='actor'):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='  ')
    assert store.writes == 0


def test_current_grants_changed_after_preview_rejects_stale_plan():
    alice = _user('alice', access_keys=('dashboard.view',))
    materializer = _Materializer((alice,))
    store = _Store((_user('alice'),))
    reconcile = AdaUsersRuntimeReconciler(materializer=materializer, store=store)
    plan = reconcile.preview()
    store.users = (replace(alice, access_keys=('dashboard.view', 'reports.read')),)

    with pytest.raises(UsersRuntimeReconciliationChangedError):
        reconcile.apply(expected_plan_id=plan.plan_id, actor='admin')
    assert store.writes == 0
