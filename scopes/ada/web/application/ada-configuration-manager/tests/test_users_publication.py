from __future__ import annotations

import pytest

from ada.web.application.configuration_manager.users_publication import (
    AdaUsersAdministrationService,
    UsersRuntimePublicationPendingError,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.errors import UserPromotionError, UsersRegistryConflictError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeProfile,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore


class Registry(UsersRegistryStore):
    def __init__(self, users):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version='r1')
        self.writes = 0

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        if self.snapshot.version != expected_version:
            raise UsersRegistryConflictError('Users registry changed')
        self.writes += 1
        self.snapshot = UsersRegistrySnapshot(users=users, version=f'r{self.writes + 1}')
        return self.snapshot


class Memberships(ToolMembershipStore):
    def __init__(self, memberships=()):
        self.snapshot = ToolMembershipSnapshot(memberships=tuple(memberships), version='m1')
        self.writes = 0

    def load(self):
        return self.snapshot

    def replace(self, memberships, *, expected_version):
        if self.snapshot.version != expected_version:
            raise UsersRegistryConflictError('Membership changed')
        self.writes += 1
        self.snapshot = ToolMembershipSnapshot(
            memberships=tuple(memberships), version=f'm{self.writes + 1}'
        )
        return self.snapshot


def identity(subject):
    return UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name=subject,
    )


def service_for(identities, memberships=()):
    registry = Registry(identities)
    store = Memberships(memberships)
    published = {}
    calls = []
    fail = {'value': False}

    def publisher(user_id):
        calls.append(user_id)
        if fail['value']:
            raise ConnectionError('Private Cosmos detail')
        found = registry.load().get(user_id)
        membership = store.load().get(user_id)
        user = RuntimeUser(
            identity=found,
            enabled=membership.enabled,
            profile=RuntimeProfile.from_profile(ProfileCatalog().require(membership.profile_key)),
        )
        published[user_id] = user
        return user

    admin = AdaUsersAdministrationService(
        registry=registry,
        memberships=store,
        profiles=lambda: ProfileCatalog(),
        publish_runtime=publisher,
    )
    return admin, registry, store, published, calls, fail


def test_promote_and_update_publish_only_the_affected_user():
    alice, bob = identity('alice'), identity('bob')
    original_bob = ToolUserMembership(user_id=bob.user_id, profile_key='basic')
    admin, registry, memberships, published, calls, _fail = service_for(
        (alice, bob), (original_bob,)
    )
    admin.promote(
        alice.user_id,
        profile_key='basic',
        expected_registry_version='r1',
        expected_membership_version='m1',
    )
    assert calls == [alice.user_id]
    assert published[alice.user_id].profile.id == 'basic'
    assert memberships.load().get(bob.user_id) == original_bob
    assert registry.writes == 0

    admin.update(
        alice.user_id,
        profile_key='root',
        enabled=False,
        expected_membership_version=memberships.load().version,
    )
    assert calls == [alice.user_id, alice.user_id]
    assert not published[alice.user_id].enabled
    assert published[alice.user_id].profile.id == 'root'
    assert memberships.load().get(bob.user_id) == original_bob


def test_runtime_failure_preserves_source_and_explicit_retry_does_not_rewrite_membership():
    alice = identity('alice')
    admin, _registry, memberships, published, calls, fail = service_for((alice,))
    fail['value'] = True
    with pytest.raises(
        UsersRuntimePublicationPendingError, match='publication is pending'
    ) as error:
        admin.promote(
            alice.user_id,
            profile_key='basic',
            expected_registry_version='r1',
            expected_membership_version='m1',
        )
    assert 'Private Cosmos detail' not in str(error.value)
    assert memberships.load().get(alice.user_id).profile_key == 'basic'
    writes = memberships.writes
    fail['value'] = False
    recovered = admin.retry_runtime(alice.user_id)
    assert recovered == published[alice.user_id]
    assert memberships.writes == writes
    assert calls == [alice.user_id, alice.user_id]


def test_stale_membership_version_never_calls_publisher():
    alice = identity('alice')
    admin, _registry, memberships, _published, calls, _fail = service_for((alice,))
    with pytest.raises(UsersRegistryConflictError):
        admin.promote(
            alice.user_id,
            profile_key='basic',
            expected_registry_version='r1',
            expected_membership_version='stale',
        )
    assert memberships.writes == 0
    assert calls == []


def test_retry_requires_managed_tool_membership():
    alice = identity('alice')
    admin, _registry, _memberships, _published, calls, _fail = service_for((alice,))
    with pytest.raises(UserPromotionError, match='managed Tool membership'):
        admin.retry_runtime(alice.user_id)
    assert calls == []
