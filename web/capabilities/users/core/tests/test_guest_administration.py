from __future__ import annotations

from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.administration import UserCandidateState, UsersAdministrationService
from atlanticus.web.users.errors import UsersRegistryConflictError
from atlanticus.web.users.models import (
    DiscoveredUser,
    ToolMembershipSnapshot,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.store import (
    ToolMembershipStore,
    UsersGuestReader,
    UsersRegistryStore,
)


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
        self.snapshot = ToolMembershipSnapshot(memberships=tuple(memberships), version=version)
        self.writes = 0

    def load(self):
        return self.snapshot

    def replace(self, memberships, *, expected_version):
        if expected_version != self.snapshot.version:
            raise UsersRegistryConflictError('membership changed')
        self.writes += 1
        self.snapshot = ToolMembershipSnapshot(
            memberships=tuple(memberships), version=f'm{self.writes + 1}'
        )
        return self.snapshot


def discovered(subject='subject'):
    return DiscoveredUser(
        issuer='issuer', subject_id=subject,
        display_name='User', email='user@example.com',
    )


class Guests(UsersGuestReader):
    def __init__(self, *users):
        self.users = tuple(users)

    def list_guests(self):
        return self.users


def test_guest_without_registry_appears_as_promotable_candidate():
    guest = discovered('new')
    registry, memberships = Registry(), Memberships()
    service = UsersAdministrationService(
        registry=registry, memberships=memberships,
        profiles=lambda: ProfileCatalog(), guest_reader=Guests(guest),
    )
    candidate = service.discover().candidates[0]
    assert candidate.state is UserCandidateState.PROMOTABLE
    promoted = service.promote(
        guest.user_id, profile_key='basic',
        expected_registry_version='r1', expected_membership_version='m1',
    )
    assert promoted.user_id == guest.user_id
    assert registry.load().get(guest.user_id) == guest.to_identity()
    assert memberships.load().get(guest.user_id) is not None


def test_global_registry_identity_takes_priority_over_observed_guest():
    global_user = discovered('existing').to_identity()
    guest = DiscoveredUser(
        issuer=global_user.issuer, subject_id=global_user.subject_id,
        display_name='Old transient name',
    )
    service = UsersAdministrationService(
        registry=Registry((global_user,)), memberships=Memberships(),
        profiles=lambda: ProfileCatalog(), guest_reader=Guests(guest),
    )
    candidate = service.discover().candidates[0]
    assert candidate.state is UserCandidateState.PROMOTABLE
    assert candidate.registry_user == global_user
