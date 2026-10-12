from __future__ import annotations

from atlanticus.web.profiles.models import BASIC_PROFILE, ProfileCatalog
from atlanticus.web.users.administration import RuntimePublicationStatus
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeProfile,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.reconstruction import UsersReconstructionPreview
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore
from ada.web.application.configuration_manager.users_publication import AdaUsersAdministrationService


class Registry(UsersRegistryStore):
    def __init__(self, identities):
        self.snapshot = UsersRegistrySnapshot(tuple(identities), 'r1')

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        raise AssertionError('Unexpected Registry write')


class Memberships(ToolMembershipStore):
    def __init__(self, users):
        self.snapshot = ToolMembershipSnapshot(
            tuple(ToolUserMembership(user_id=user.user_id, profile_key='basic') for user in users),
            'm1',
        )

    def load(self):
        return self.snapshot

    def replace(self, memberships, *, expected_version):
        raise AssertionError('Unexpected Membership write')


def user(subject):
    identity = UserIdentity(
        user_id=build_user_key(issuer='test-issuer', subject_id=subject),
        issuer='test-issuer', subject_id=subject, display_name=subject,
    )
    return RuntimeUser(
        identity=identity, enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


def administration(users, inspect):
    return AdaUsersAdministrationService(
        registry=Registry(user.identity for user in users),
        memberships=Memberships(users),
        profiles=lambda: ProfileCatalog(),
        publish_runtime=lambda user_id: next(user for user in users if user.user_id == user_id),
        inspect_runtime=inspect,
    )


def test_runtime_statuses_are_independent_of_promoted_membership():
    missing, outdated, synchronized = user('missing'), user('outdated'), user('synchronized')
    preview = UsersReconstructionPreview(
        desired_users=(missing, outdated, synchronized),
        create_ids=(missing.user_id,), update_ids=(outdated.user_id,), disable_ids=(),
    )
    service = administration((missing, outdated, synchronized), lambda: preview)
    statuses = {candidate.user_id: candidate.runtime_status for candidate in service.discover().candidates}
    assert statuses == {
        missing.user_id: RuntimePublicationStatus.MISSING,
        outdated.user_id: RuntimePublicationStatus.OUTDATED,
        synchronized.user_id: RuntimePublicationStatus.SYNCHRONIZED,
    }


def test_inspection_failure_never_claims_runtime_is_synchronized():
    managed = user('managed')

    def unavailable():
        raise RuntimeError('unavailable')

    candidates = administration((managed,), unavailable).discover().candidates
    assert candidates[0].runtime_status is RuntimePublicationStatus.UNAVAILABLE
