from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.administration import UserCandidateState, UsersAdministrationService
from atlanticus.web.users.errors import (
    UserAlreadyPromotedError,
    UserPromotionError,
    UsersDefinitionError,
    UsersRegistryConflictError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import DiscoveredUser, UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import (
    UsersAdministrationStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)


def profiles() -> ProfileCatalog:
    return ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='11111111-1111-4111-8111-111111111111',
                label='Analista',
                background_color='#112233',
            ),
        )
    )


def user(
    subject: str,
    *,
    email: str | None = None,
    name: str | None = None,
    profile_key: str = 'basic',
    enabled: bool = True,
) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra',
        subject_id=subject,
        display_name=name or f'User {subject}',
        email=email,
        enabled=enabled,
        profile_key=profile_key,
    )


def discovered(subject: str, *, email: str | None = None, name: str | None = None) -> DiscoveredUser:
    return DiscoveredUser(
        issuer='entra',
        subject_id=subject,
        display_name=name or f'User {subject}',
        email=email,
    )


class MemoryRegistry(UsersRegistryStore):
    def __init__(self, users=(), version='v1'):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version=version)
        self.replaces = 0

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        if self.snapshot.version != expected_version:
            raise UsersRegistryConflictError('conflict')
        self.replaces += 1
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version=f'v{self.replaces + 1}')
        return self.snapshot


class MemoryPromoted(UsersAdministrationStore):
    def __init__(self, users=()):
        self.users = {value.user_id: value for value in users}
        self.creates = 0
        self.replaces = 0

    def get(self, user_id):
        return self.users.get(user_id)

    def list_users(self):
        return tuple(self.users.values())

    def create(self, value):
        if value.user_id in self.users:
            raise UserAlreadyPromotedError
        self.creates += 1
        self.users[value.user_id] = value
        return value

    def replace(self, value):
        self.replaces += 1
        self.users[value.user_id] = value
        return value


class MemoryDirectory(UsersDirectoryReader):
    def __init__(self, users=()):
        self.users = tuple(users)

    def list_discovered(self):
        return self.users


def service(*, registry=None, promoted=None, directory=None) -> UsersAdministrationService:
    return UsersAdministrationService(
        registry=registry or MemoryRegistry(),
        promoted=promoted or MemoryPromoted(),
        profiles=profiles,
        directory=directory,
    )


def test_administration_exposes_only_assignable_profile_catalog() -> None:
    snapshot = service().discover()

    assert tuple(profile.key for profile in snapshot.profiles) == (
        'basic',
        'root',
        '11111111-1111-4111-8111-111111111111',
    )


def test_administration_accepts_configured_profile_and_rejects_unknown_profile() -> None:
    configured = user('1', profile_key='11111111-1111-4111-8111-111111111111')
    promoted = MemoryPromoted()
    registry = MemoryRegistry([configured])
    assert service(registry=registry, promoted=promoted).promote(
        configured.user_id,
        profile_key=configured.profile_key,
        expected_registry_version='v1',
    ) == configured

    unknown = user('2', profile_key='basic')
    with pytest.raises(UsersDefinitionError, match='Unknown managed user profile'):
        service(registry=MemoryRegistry([unknown])).promote(
            unknown.user_id,
            profile_key='missing',
            expected_registry_version='v1',
        )


def test_administration_rejects_guest_for_promotion_and_update() -> None:
    pending = user('pending', profile_key='guest')
    with pytest.raises(UsersDefinitionError, match='must not be guest'):
        service(registry=MemoryRegistry([pending])).promote(
            pending.user_id,
            profile_key='guest',
            expected_registry_version='v1',
        )

    promoted_user = user('managed', profile_key='basic')
    with pytest.raises(UsersDefinitionError, match='must not be guest'):
        service(
            registry=MemoryRegistry([promoted_user]),
            promoted=MemoryPromoted([promoted_user]),
        ).update(
            promoted_user.user_id,
            profile_key='guest',
            enabled=True,
            expected_registry_version='v1',
        )


def test_discovery_marks_cosmos_presence_as_promoted_even_when_storage_differs():
    storage_user = user('1', email='old@example.com')
    promoted_user = user('1', email='new@example.com')
    candidate = service(
        registry=MemoryRegistry([storage_user]),
        promoted=MemoryPromoted([promoted_user]),
        directory=MemoryDirectory([discovered('1', email='entra@example.com')]),
    ).discover().candidates[0]
    assert candidate.state is UserCandidateState.PROMOTED
    assert 'Promoted user differs from durable registry' in candidate.issues
    assert 'Directory data differs from promoted user' in candidate.issues


def test_discovery_marks_storage_directory_difference_as_conflict():
    candidate = service(
        registry=MemoryRegistry([user('1', email='storage@example.com')]),
        directory=MemoryDirectory([discovered('1', email='entra@example.com')]),
    ).discover().candidates[0]
    assert candidate.state is UserCandidateState.CONFLICT


def test_email_match_on_different_strong_identity_is_conflict_not_merge():
    candidates = service(
        registry=MemoryRegistry([user('storage', email='same@example.com')]),
        directory=MemoryDirectory([discovered('entra', email='same@example.com')]),
    ).discover().candidates
    assert len(candidates) == 2
    assert {candidate.state for candidate in candidates} == {UserCandidateState.CONFLICT}
    assert all(
        'Email matches a different user identity' in candidate.issues for candidate in candidates
    )


def test_promote_from_storage_only_changes_administrative_fields() -> None:
    durable = user('1', email='user@example.com', profile_key='guest', enabled=False)
    registry = MemoryRegistry([durable])
    promoted = MemoryPromoted()
    result = service(registry=registry, promoted=promoted).promote(
        durable.user_id,
        profile_key='basic',
        enabled=True,
        expected_registry_version='v1',
    )
    assert result == replace(durable, profile_key='basic', enabled=True)
    assert registry.replaces == 1
    assert promoted.creates == 1


def test_promote_from_directory_persists_storage_before_cosmos():
    candidate = discovered('1', email='user@example.com')
    registry = MemoryRegistry([], version='v1')
    promoted = MemoryPromoted()
    result = service(
        registry=registry,
        promoted=promoted,
        directory=MemoryDirectory([candidate]),
    ).promote(
        candidate.user_id,
        profile_key='basic',
        expected_registry_version='v1',
    )
    expected = candidate.promote_as(profile_key='basic')
    assert result == expected
    assert registry.snapshot.get(expected.user_id) == expected
    assert promoted.get(expected.user_id) == expected


def test_promote_is_forbidden_when_cosmos_already_contains_user():
    durable = user('1')
    with pytest.raises(UserAlreadyPromotedError):
        service(
            registry=MemoryRegistry([durable]),
            promoted=MemoryPromoted([durable]),
        ).promote(
            durable.user_id,
            profile_key='basic',
            expected_registry_version='v1',
        )


def test_promote_blocks_conflicted_candidate():
    storage = user('1', email='storage@example.com')
    directory = discovered('1', email='entra@example.com')

    with pytest.raises(UserPromotionError, match='unresolved conflicts'):
        service(
            registry=MemoryRegistry([storage]),
            directory=MemoryDirectory([directory]),
        ).promote(
            storage.user_id,
            profile_key='basic',
            expected_registry_version='v1',
        )


def test_promote_blocks_same_email_on_different_strong_identity():
    storage = user('storage', email='same@example.com')
    directory = discovered('entra', email='same@example.com')

    with pytest.raises(UserPromotionError):
        service(
            registry=MemoryRegistry([storage]),
            directory=MemoryDirectory([directory]),
        ).promote(
            directory.user_id,
            profile_key='basic',
            expected_registry_version='v1',
        )


def test_update_changes_only_profile_and_enabled() -> None:
    original = user('1', email='promoted@example.com', name='Promoted Name', profile_key='basic')
    registry_version = replace(original, email='registry@example.com', display_name='Registry Name')
    registry = MemoryRegistry([registry_version])
    promoted = MemoryPromoted([original])

    result = service(registry=registry, promoted=promoted).update(
        original.user_id,
        profile_key='11111111-1111-4111-8111-111111111111',
        enabled=False,
        expected_registry_version='v1',
    )

    assert result == replace(
        original,
        profile_key='11111111-1111-4111-8111-111111111111',
        enabled=False,
    )
    assert registry.snapshot.get(original.user_id) == replace(
        registry_version,
        profile_key='11111111-1111-4111-8111-111111111111',
        enabled=False,
    )
