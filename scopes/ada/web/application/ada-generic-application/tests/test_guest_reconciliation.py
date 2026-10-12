from __future__ import annotations

from dataclasses import replace

from ada.web.application.generic.users_reconciliation import AdaUsersReconciliationWorkflow
from ada.web.application.configuration_manager.local_runtime import InProcessUsersRuntimeStore
from atlanticus.web.profiles.models import BASIC_PROFILE, GUEST_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


class Materializer:
    def __init__(self, users):
        self.users = users

    def materialize_all(self):
        return tuple(self.users)

    def materialize_user(self, user_id):
        return next(user for user in self.users if user.user_id == user_id)


def _user(subject, profile):
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer', subject_id=subject, display_name=subject,
    )
    return RuntimeUser(identity=identity, enabled=True, profile=RuntimeProfile.from_profile(profile))


def test_guest_matching_promoted_membership_is_update_not_create():
    guest = _user('alice', GUEST_PROFILE)
    desired = replace(guest, profile=RuntimeProfile.from_profile(BASIC_PROFILE))
    runtime = InProcessUsersRuntimeStore((guest,))
    workflow = AdaUsersReconciliationWorkflow(materializer=Materializer((desired,)), runtime=runtime)
    preview = workflow.inspect()
    assert preview.create_ids == ()
    assert preview.update_ids == (guest.user_id,)
    assert preview.disable_ids == ()
    assert not workflow.apply(preview).has_changes
    assert runtime.list_users() == (desired,)
    assert not workflow.inspect().has_changes


def test_guest_without_membership_is_preserved_during_reconciliation():
    guest = _user('newcomer', GUEST_PROFILE)
    runtime = InProcessUsersRuntimeStore((guest,))
    workflow = AdaUsersReconciliationWorkflow(materializer=Materializer(()), runtime=runtime)
    assert not workflow.inspect().has_changes
    assert not workflow.apply(workflow.inspect()).has_changes
    assert runtime.list_users() == (guest,)


def test_earlier_environment_profile_overwrites_guest_at_destination():
    guest = _user('alice', GUEST_PROFILE)
    desired = replace(guest, profile=RuntimeProfile.from_profile(ROOT_PROFILE))
    runtime = InProcessUsersRuntimeStore((guest,))
    workflow = AdaUsersReconciliationWorkflow(materializer=Materializer((desired,)), runtime=runtime)
    assert workflow.inspect().update_ids == (guest.user_id,)
    workflow.apply(workflow.inspect())
    assert runtime.list_users() == (desired,)
