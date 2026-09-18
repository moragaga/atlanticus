from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from atlanticus.web.users.errors import (
    UserAlreadyPromotedError,
    UserPromotionError,
    UsersIdentityConflictError,
    UsersRegistryConflictError,
)
from atlanticus.web.users.models import DiscoveredUser, UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import (
    UsersAdministrationStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)


class UserCandidateState(StrEnum):
    PROMOTABLE = 'promotable'
    CONFLICT = 'conflict'
    PROMOTED = 'promoted'


@dataclass(frozen=True, slots=True)
class UserCandidate:
    user_id: str
    state: UserCandidateState
    registry_user: UserRecord | None = None
    directory_user: DiscoveredUser | None = None
    promoted_user: UserRecord | None = None
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        user_id = self.user_id.strip()
        if not user_id:
            raise ValueError('User candidate id must not be empty')
        object.__setattr__(self, 'user_id', user_id)
        object.__setattr__(self, 'issues', tuple(self.issues))


@dataclass(frozen=True, slots=True)
class UsersAdministrationSnapshot:
    registry: UsersRegistrySnapshot
    candidates: tuple[UserCandidate, ...]


class UsersAdministrationService:
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        promoted: UsersAdministrationStore,
        directory: UsersDirectoryReader | None = None,
    ) -> None:
        self._registry = registry
        self._promoted = promoted
        self._directory = directory

    def discover(self) -> UsersAdministrationSnapshot:
        registry = self._registry.load()
        promoted_users = self._promoted.list_users()
        directory_users = self._directory.list_discovered() if self._directory is not None else ()
        return UsersAdministrationSnapshot(
            registry=registry,
            candidates=_resolve_candidates(
                registry_users=registry.users,
                promoted_users=promoted_users,
                directory_users=directory_users,
            ),
        )

    def promote(
        self,
        user: UserRecord,
        *,
        expected_registry_version: str | None,
    ) -> UserRecord:
        if not isinstance(user, UserRecord):
            raise TypeError('user must be UserRecord')
        if self._promoted.get(user.user_id) is not None:
            raise UserAlreadyPromotedError('User is already promoted')
        _require_no_cross_identity_email_conflict(user, self.discover().candidates)

        registry = self._registry.load()
        registry_user = registry.get(user.user_id)
        directory_user = self._find_directory_user(user.user_id)
        if registry_user is None and directory_user is None:
            raise UserPromotionError('User is not available from storage or directory discovery')
        _require_promotion_identity(
            user=user,
            registry_user=registry_user,
            directory_user=directory_user,
        )

        if registry_user != user:
            if registry.version != expected_registry_version:
                raise UsersRegistryConflictError('Users registry changed before promotion')
            users = _replace_registry_user(registry.users, user)
            registry = self._registry.replace(
                users,
                expected_version=expected_registry_version,
            )
            persisted = registry.get(user.user_id)
            if persisted != user:
                raise UserPromotionError('Users registry persisted a different user')

        if self._promoted.get(user.user_id) is not None:
            raise UserAlreadyPromotedError('User was promoted concurrently')
        return self._promoted.create(user)

    def update(
        self,
        user: UserRecord,
        *,
        expected_registry_version: str,
    ) -> UserRecord:
        if not isinstance(user, UserRecord):
            raise TypeError('user must be UserRecord')
        current = self._promoted.get(user.user_id)
        if current is None:
            raise UserPromotionError('Promoted user does not exist')
        if (current.issuer, current.subject_id) != (user.issuer, user.subject_id):
            raise UsersIdentityConflictError('Promoted user identity cannot be changed')
        registry = self._registry.load()
        registry_user = registry.get(user.user_id)
        if registry_user is None:
            raise UserPromotionError('Promoted user is missing from users registry')
        if registry.version != expected_registry_version:
            raise UsersRegistryConflictError('Users registry changed before user update')
        updated_registry = self._registry.replace(
            _replace_registry_user(registry.users, user),
            expected_version=expected_registry_version,
        )
        if updated_registry.get(user.user_id) != user:
            raise UserPromotionError('Users registry persisted a different user')
        return self._promoted.replace(user)

    def _find_directory_user(self, user_id: str) -> DiscoveredUser | None:
        if self._directory is None:
            return None
        return next(
            (user for user in self._directory.list_discovered() if user.user_id == user_id),
            None,
        )


def _resolve_candidates(
    *,
    registry_users: tuple[UserRecord, ...],
    promoted_users: tuple[UserRecord, ...],
    directory_users: tuple[DiscoveredUser, ...],
) -> tuple[UserCandidate, ...]:
    registry_by_id = {user.user_id: user for user in registry_users}
    promoted_by_id = {user.user_id: user for user in promoted_users}
    directory_by_id = {user.user_id: user for user in directory_users}
    user_ids = sorted(set(registry_by_id) | set(promoted_by_id) | set(directory_by_id))
    candidates: dict[str, UserCandidate] = {}

    for user_id in user_ids:
        registry_user = registry_by_id.get(user_id)
        promoted_user = promoted_by_id.get(user_id)
        directory_user = directory_by_id.get(user_id)
        issues: list[str] = []
        if promoted_user is not None:
            state = UserCandidateState.PROMOTED
            if registry_user is None:
                issues.append('Promoted user is missing from durable registry')
            elif registry_user != promoted_user:
                issues.append('Promoted user differs from durable registry')
            if directory_user is not None and not _directory_matches_user(directory_user, promoted_user):
                issues.append('Directory data differs from promoted user')
        else:
            state = UserCandidateState.PROMOTABLE
            if registry_user is not None and directory_user is not None:
                if not _directory_matches_user(directory_user, registry_user):
                    state = UserCandidateState.CONFLICT
                    issues.append('Directory data differs from durable registry')
        candidates[user_id] = UserCandidate(
            user_id=user_id,
            state=state,
            registry_user=registry_user,
            directory_user=directory_user,
            promoted_user=promoted_user,
            issues=tuple(issues),
        )

    email_index: dict[str, set[str]] = {}
    for user_id, candidate in candidates.items():
        for email in _candidate_emails(candidate):
            email_index.setdefault(email, set()).add(user_id)
    conflicting_ids = {
        user_id
        for user_ids_for_email in email_index.values()
        if len(user_ids_for_email) > 1
        for user_id in user_ids_for_email
    }
    for user_id in conflicting_ids:
        candidate = candidates[user_id]
        issues = (*candidate.issues, 'Email matches a different user identity')
        state = (
            candidate.state
            if candidate.state is UserCandidateState.PROMOTED
            else UserCandidateState.CONFLICT
        )
        candidates[user_id] = replace(candidate, state=state, issues=issues)

    return tuple(candidates[user_id] for user_id in sorted(candidates))


def _candidate_emails(candidate: UserCandidate) -> tuple[str, ...]:
    values = {
        email
        for email in (
            candidate.registry_user.email if candidate.registry_user is not None else None,
            candidate.directory_user.email if candidate.directory_user is not None else None,
            candidate.promoted_user.email if candidate.promoted_user is not None else None,
        )
        if email is not None
    }
    return tuple(values)


def _directory_matches_user(directory: DiscoveredUser, user: UserRecord) -> bool:
    return (
        directory.issuer == user.issuer
        and directory.subject_id == user.subject_id
        and directory.display_name == user.display_name
        and directory.email == user.email
    )


def _require_promotion_identity(
    *,
    user: UserRecord,
    registry_user: UserRecord | None,
    directory_user: DiscoveredUser | None,
) -> None:
    if registry_user is not None and (
        registry_user.issuer != user.issuer or registry_user.subject_id != user.subject_id
    ):
        raise UsersIdentityConflictError('User identity conflicts with durable registry')
    if directory_user is not None and (
        directory_user.issuer != user.issuer or directory_user.subject_id != user.subject_id
    ):
        raise UsersIdentityConflictError('User identity conflicts with directory discovery')


def _replace_registry_user(
    users: tuple[UserRecord, ...],
    user: UserRecord,
) -> tuple[UserRecord, ...]:
    replaced = False
    result: list[UserRecord] = []
    for current in users:
        if current.user_id == user.user_id:
            result.append(user)
            replaced = True
        else:
            result.append(current)
    if not replaced:
        result.append(user)
    return tuple(result)


def _require_no_cross_identity_email_conflict(
    user: UserRecord,
    candidates: tuple[UserCandidate, ...],
) -> None:
    if user.email is None:
        return
    for candidate in candidates:
        if candidate.user_id == user.user_id:
            continue
        if user.email in _candidate_emails(candidate):
            raise UserPromotionError('User email conflicts with a different identity')
