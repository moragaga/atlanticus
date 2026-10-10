import pytest

from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.administration import UserCandidateState, UsersAdministrationService
from atlanticus.web.users.errors import UserPromotionError, UsersRegistryConflictError
from atlanticus.web.users.models import (
    DiscoveredUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersDirectoryReader, UsersRegistryStore


class Registry(UsersRegistryStore):
    def __init__(self, users=(), version='r1'):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version=version)
        self.writes = 0

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        if expected_version != self.snapshot.version:
            raise UsersRegistryConflictError('registry changed')
        self.writes += 1
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version=f'r{self.writes + 1}')
        return self.snapshot


class Memberships(ToolMembershipStore):
    def __init__(self, memberships=(), version='m1'):
        self.snapshot = ToolMembershipSnapshot(
            memberships=tuple(memberships),
            version=version,
        )
        self.writes = 0

    def load(self):
        return self.snapshot

    def replace(self, memberships, *, expected_version):
        if expected_version != self.snapshot.version:
            raise UsersRegistryConflictError('membership changed')
        self.writes += 1
        self.snapshot = ToolMembershipSnapshot(
            memberships=tuple(memberships),
            version=f'm{self.writes + 1}',
        )
        return self.snapshot


class Directory(UsersDirectoryReader):
    def __init__(self, *users):
        self.users = tuple(users)

    def list_discovered(self):
        return self.users


def discovered(subject='subject') -> DiscoveredUser:
    return DiscoveredUser(
        issuer='issuer',
        subject_id=subject,
        display_name='User',
        email='user@example.com',
    )


def test_promote_persists_global_identity_and_tool_membership_separately():
    registry = Registry()
    memberships = Memberships()
    user = discovered()
    service = UsersAdministrationService(
        registry=registry,
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
        directory=Directory(user),
    )
    promoted = service.promote(
        user.user_id,
        profile_key='root',
        expected_registry_version='r1',
        expected_membership_version='m1',
    )
    assert promoted.identity == registry.load().get(user.user_id)
    assert promoted.membership == memberships.load().get(user.user_id)
    assert promoted.profile_key == 'root'


def test_update_changes_membership_only():
    identity = discovered().to_identity()
    registry = Registry((identity,))
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='basic')
    memberships = Memberships((membership,))
    service = UsersAdministrationService(
        registry=registry,
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
    )
    updated = service.update(
        identity.user_id,
        profile_key='root',
        enabled=False,
        expected_membership_version='m1',
    )
    assert registry.writes == 0
    assert updated.profile_key == 'root'
    assert not updated.enabled


def test_membership_without_global_identity_is_reported_as_conflict():
    membership = ToolUserMembership(user_id='missing-user', profile_key='basic')
    service = UsersAdministrationService(
        registry=Registry(),
        memberships=Memberships((membership,)),
        profiles=lambda: ProfileCatalog(),
    )
    candidate = service.discover().candidates[0]
    assert candidate.state is UserCandidateState.CONFLICT
    assert 'missing global identity' in candidate.issues[0]


def test_unknown_user_cannot_be_promoted():
    service = UsersAdministrationService(
        registry=Registry(),
        memberships=Memberships(),
        profiles=lambda: ProfileCatalog(),
    )
    with pytest.raises(UserPromotionError):
        service.promote(
            'missing',
            profile_key='basic',
            expected_registry_version='r1',
            expected_membership_version='m1',
        )


def test_promotion_rejects_stale_tool_membership_before_creating_global_identity():
    registry = Registry()
    memberships = Memberships(version='m2')
    user = discovered()
    service = UsersAdministrationService(
        registry=registry,
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
        directory=Directory(user),
    )
    with pytest.raises(UsersRegistryConflictError, match='Tool membership changed'):
        service.promote(
            user.user_id,
            profile_key='basic',
            expected_registry_version='r1',
            expected_membership_version='m1',
        )
    assert registry.writes == 0
    assert memberships.writes == 0


def test_update_rejects_stale_membership_without_overwriting_another_change():
    identity = discovered().to_identity()
    registry = Registry((identity,))
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='basic')
    memberships = Memberships((membership,), version='m2')
    service = UsersAdministrationService(
        registry=registry,
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
    )
    with pytest.raises(UsersRegistryConflictError, match='Tool membership changed'):
        service.update(
            identity.user_id,
            profile_key='root',
            enabled=False,
            expected_membership_version='m1',
        )
    assert memberships.writes == 0
    assert memberships.load().get(identity.user_id) == membership


def test_promotion_allows_explicit_empty_membership_version_on_first_write():
    registry = Registry(version=None)
    memberships = Memberships(version=None)
    user = discovered()
    service = UsersAdministrationService(
        registry=registry,
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
        directory=Directory(user),
    )
    promoted = service.promote(
        user.user_id,
        profile_key='basic',
        expected_registry_version=None,
        expected_membership_version=None,
    )
    assert promoted.membership == memberships.load().get(user.user_id)
    assert registry.writes == 1
    assert memberships.writes == 1
