from __future__ import annotations

from dataclasses import replace

import pytest

from atlanticus.web.users.administration import UserCandidateState, UsersAdministrationService
from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY, ROOT_AUTHORITY_KEY
from atlanticus.web.users.errors import (
    UserAlreadyPromotedError,
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


def user(subject: str, *, email: str | None = None, name: str | None = None) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra',
        subject_id=subject,
        display_name=name or f'User {subject}',
        email=email,
        enabled=True,
        authority_key=BASIC_AUTHORITY_KEY,
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


def test_managed_users_only_accept_global_assignable_authority():
    with pytest.raises(UsersDefinitionError, match='basic or root'):
        replace(user('1'), authority_key='operator')
    assert replace(user('1'), authority_key=ROOT_AUTHORITY_KEY).authority_key == 'root'


def test_discovery_marks_cosmos_presence_as_promoted_even_when_storage_differs():
    storage_user = user('1', email='old@example.com')
    promoted_user = user('1', email='new@example.com')
    service = UsersAdministrationService(
        registry=MemoryRegistry([storage_user]),
        promoted=MemoryPromoted([promoted_user]),
        directory=MemoryDirectory([discovered('1', email='entra@example.com')]),
    )
    candidate = service.discover().candidates[0]
    assert candidate.state is UserCandidateState.PROMOTED
    assert 'Promoted user differs from durable registry' in candidate.issues
    assert 'Directory data differs from promoted user' in candidate.issues


def test_discovery_marks_storage_directory_difference_as_conflict():
    service = UsersAdministrationService(
        registry=MemoryRegistry([user('1', email='storage@example.com')]),
        promoted=MemoryPromoted(),
        directory=MemoryDirectory([discovered('1', email='entra@example.com')]),
    )
    candidate = service.discover().candidates[0]
    assert candidate.state is UserCandidateState.CONFLICT


def test_email_match_on_different_strong_identity_is_conflict_not_merge():
    service = UsersAdministrationService(
        registry=MemoryRegistry([user('storage', email='same@example.com')]),
        promoted=MemoryPromoted(),
        directory=MemoryDirectory([discovered('entra', email='same@example.com')]),
    )
    candidates = service.discover().candidates
    assert len(candidates) == 2
    assert {candidate.state for candidate in candidates} == {UserCandidateState.CONFLICT}
    assert all('Email matches a different user identity' in candidate.issues for candidate in candidates)


def test_promote_from_storage_does_not_rewrite_registry():
    durable = user('1')
    registry = MemoryRegistry([durable])
    promoted = MemoryPromoted()
    service = UsersAdministrationService(registry=registry, promoted=promoted)
    result = service.promote(durable, expected_registry_version='v1')
    assert result == durable
    assert registry.replaces == 0
    assert promoted.creates == 1


def test_promote_from_directory_persists_storage_before_cosmos():
    candidate = discovered('1', email='user@example.com')
    durable = candidate.promote_as(authority_key=BASIC_AUTHORITY_KEY)
    registry = MemoryRegistry([], version='v1')
    promoted = MemoryPromoted()
    service = UsersAdministrationService(
        registry=registry,
        promoted=promoted,
        directory=MemoryDirectory([candidate]),
    )
    result = service.promote(durable, expected_registry_version='v1')
    assert result == durable
    assert registry.snapshot.get(durable.user_id) == durable
    assert promoted.get(durable.user_id) == durable


def test_promote_is_forbidden_when_cosmos_already_contains_user():
    durable = user('1')
    service = UsersAdministrationService(
        registry=MemoryRegistry([durable]),
        promoted=MemoryPromoted([durable]),
    )
    with pytest.raises(UserAlreadyPromotedError):
        service.promote(durable, expected_registry_version='v1')


def test_promote_blocks_same_email_on_different_strong_identity():
    storage = user('storage', email='same@example.com')
    directory = discovered('entra', email='same@example.com')
    service = UsersAdministrationService(
        registry=MemoryRegistry([storage]),
        promoted=MemoryPromoted(),
        directory=MemoryDirectory([directory]),
    )
    proposed = directory.promote_as(authority_key=BASIC_AUTHORITY_KEY)

    from atlanticus.web.users.errors import UserPromotionError

    with pytest.raises(UserPromotionError, match='different identity'):
        service.promote(proposed, expected_registry_version='v1')
