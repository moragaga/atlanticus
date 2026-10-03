from __future__ import annotations

# La administración compone identidad global con membership Tool sin duplicar ownership.

from dataclasses import dataclass
from enum import StrEnum

from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.errors import (
    UserAlreadyPromotedError,
    UserPromotionError,
    UsersIdentityConflictError,
    UsersRegistryConflictError,
)
from atlanticus.web.users.models import (
    DiscoveredUser,
    ManagedUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.profiles import (
    UsersProfileCatalogProvider,
    available_managed_profiles,
    require_managed_profile,
    resolve_profile_catalog,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersDirectoryReader, UsersRegistryStore


class UserCandidateState(StrEnum):
    PROMOTABLE = 'promotable'
    CONFLICT = 'conflict'
    PROMOTED = 'promoted'


@dataclass(frozen=True, slots=True)
class UserCandidate:
    user_id: str
    state: UserCandidateState
    registry_user: UserIdentity | None = None
    directory_user: DiscoveredUser | None = None
    promoted_user: ManagedUser | None = None
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
    memberships: ToolMembershipSnapshot
    candidates: tuple[UserCandidate, ...]
    profiles: tuple[ProfileDefinition, ...]


class UsersAdministrationService:
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        memberships: ToolMembershipStore,
        profiles: UsersProfileCatalogProvider,
        directory: UsersDirectoryReader | None = None,
    ) -> None:
        self._registry = registry
        self._memberships = memberships
        self._profiles = profiles
        self._directory = directory

    def available_profiles(self) -> tuple[ProfileDefinition, ...]:
        return available_managed_profiles(resolve_profile_catalog(self._profiles))

    def discover(self) -> UsersAdministrationSnapshot:
        registry = self._registry.load()
        memberships = self._memberships.load()
        directory_users = self._directory.list_discovered() if self._directory is not None else ()
        return UsersAdministrationSnapshot(
            registry=registry,
            memberships=memberships,
            candidates=_resolve_candidates(
                registry=registry,
                memberships=memberships,
                directory_users=directory_users,
            ),
            profiles=self.available_profiles(),
        )

    def managed_users(self) -> tuple[ManagedUser, ...]:
        snapshot = self.discover()
        return tuple(
            candidate.promoted_user
            for candidate in snapshot.candidates
            if candidate.promoted_user is not None
        )

    def promote(
        self,
        user_id: str,
        *,
        profile_key: str,
        enabled: bool = True,
        expected_registry_version: str | None,
        expected_membership_version: str | None = None,
    ) -> ManagedUser:
        normalized_user_id = _required_user_id(user_id)
        profile = require_managed_profile(profile_key, profiles=resolve_profile_catalog(self._profiles))
        if not isinstance(enabled, bool):
            raise TypeError('enabled must be boolean')

        snapshot = self.discover()
        candidate = next(
            (item for item in snapshot.candidates if item.user_id == normalized_user_id),
            None,
        )
        if candidate is None:
            raise UserPromotionError('User is not available from storage or directory discovery')
        if candidate.state is UserCandidateState.PROMOTED:
            raise UserAlreadyPromotedError('User is already promoted')
        if candidate.state is UserCandidateState.CONFLICT:
            raise UserPromotionError('User candidate has unresolved conflicts')

        identity = candidate.registry_user
        if identity is None:
            if candidate.directory_user is None:
                raise UserPromotionError('User identity is not available')
            identity = candidate.directory_user.to_identity()
            if snapshot.registry.version != expected_registry_version:
                raise UsersRegistryConflictError('Users registry changed before promotion')
            updated_registry = self._registry.replace(
                (*snapshot.registry.users, identity),
                expected_version=expected_registry_version,
            )
            persisted = updated_registry.get(identity.user_id)
            if persisted != identity:
                raise UserPromotionError('Users registry persisted a different identity')
            snapshot = self.discover()
        elif candidate.directory_user is not None:
            _require_directory_identity(candidate.directory_user, identity)

        memberships = snapshot.memberships
        expected_membership_version = (
            memberships.version
            if expected_membership_version is None
            else expected_membership_version
        )
        if memberships.version != expected_membership_version:
            raise UsersRegistryConflictError('Tool membership changed before promotion')
        if memberships.get(identity.user_id) is not None:
            raise UserAlreadyPromotedError('User was promoted concurrently')
        membership = ToolUserMembership(
            user_id=identity.user_id,
            profile_key=profile.key,
            enabled=enabled,
        )
        saved = self._memberships.replace(
            (*memberships.memberships, membership),
            expected_version=expected_membership_version,
        )
        persisted_membership = saved.get(identity.user_id)
        if persisted_membership != membership:
            raise UserPromotionError('Tool membership persisted a different user')
        return ManagedUser(identity=identity, membership=membership)

    def update(
        self,
        user_id: str,
        *,
        profile_key: str,
        enabled: bool,
        expected_registry_version: str | None = None,
        expected_membership_version: str | None = None,
    ) -> ManagedUser:
        del expected_registry_version
        normalized_user_id = _required_user_id(user_id)
        profile = require_managed_profile(profile_key, profiles=resolve_profile_catalog(self._profiles))
        if not isinstance(enabled, bool):
            raise TypeError('enabled must be boolean')

        registry = self._registry.load()
        identity = registry.get(normalized_user_id)
        if identity is None:
            raise UserPromotionError('Managed user is missing from users registry')
        memberships = self._memberships.load()
        current = memberships.get(normalized_user_id)
        if current is None:
            raise UserPromotionError('Managed user does not exist')
        expected = memberships.version if expected_membership_version is None else expected_membership_version
        if memberships.version != expected:
            raise UsersRegistryConflictError('Tool membership changed before user update')
        updated = ToolUserMembership(
            user_id=normalized_user_id,
            profile_key=profile.key,
            enabled=enabled,
        )
        saved = self._memberships.replace(
            tuple(
                updated if item.user_id == normalized_user_id else item
                for item in memberships.memberships
            ),
            expected_version=expected,
        )
        if saved.get(normalized_user_id) != updated:
            raise UserPromotionError('Tool membership persisted a different user')
        return ManagedUser(identity=identity, membership=updated)


def _resolve_candidates(
    *,
    registry: UsersRegistrySnapshot,
    memberships: ToolMembershipSnapshot,
    directory_users: tuple[DiscoveredUser, ...],
) -> tuple[UserCandidate, ...]:
    registry_by_id = {user.user_id: user for user in registry.users}
    membership_by_id = {item.user_id: item for item in memberships.memberships}
    directory_by_id = {user.user_id: user for user in directory_users}
    user_ids = sorted(set(registry_by_id) | set(membership_by_id) | set(directory_by_id))
    candidates: list[UserCandidate] = []

    for user_id in user_ids:
        identity = registry_by_id.get(user_id)
        membership = membership_by_id.get(user_id)
        directory = directory_by_id.get(user_id)
        issues: list[str] = []
        state = UserCandidateState.PROMOTABLE

        if membership is not None:
            if identity is None:
                state = UserCandidateState.CONFLICT
                issues.append('Tool membership is missing global identity')
                promoted = None
            else:
                promoted = ManagedUser(identity=identity, membership=membership)
                state = UserCandidateState.PROMOTED
        else:
            promoted = None

        if identity is not None and directory is not None:
            if not _directory_matches_identity(directory, identity):
                state = UserCandidateState.CONFLICT
                issues.append('Directory data differs from durable identity')

        candidates.append(
            UserCandidate(
                user_id=user_id,
                state=state,
                registry_user=identity,
                directory_user=directory,
                promoted_user=promoted,
                issues=tuple(issues),
            )
        )
    return tuple(candidates)


def _directory_matches_identity(directory: DiscoveredUser, identity: UserIdentity) -> bool:
    return (
        directory.issuer == identity.issuer
        and directory.subject_id == identity.subject_id
        and (directory.display_name is None or directory.display_name == identity.display_name)
        and (directory.email is None or directory.email == identity.email)
    )


def _require_directory_identity(directory: DiscoveredUser, identity: UserIdentity) -> None:
    if directory.issuer != identity.issuer or directory.subject_id != identity.subject_id:
        raise UsersIdentityConflictError('User identity conflicts with directory discovery')


def _required_user_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError('user_id must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise UserPromotionError('User id has an invalid format')
    return normalized
