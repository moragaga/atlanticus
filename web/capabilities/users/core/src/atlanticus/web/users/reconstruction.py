from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from atlanticus.web.profiles.models import GUEST_PROFILE_KEY
from atlanticus.web.users.models import RuntimeUser, build_runtime_user
from atlanticus.web.users.profiles import (
    UsersProfileCatalogProvider,
    require_managed_profile,
    resolve_profile_catalog,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore, UsersRuntimeStore


class UsersReconstructionConflictError(RuntimeError):
    pass


class UsersBaseRuntimeWriter(Protocol):
    def upsert_base_user(self, user: RuntimeUser) -> RuntimeUser: ...


@dataclass(frozen=True, slots=True)
class UsersReconstructionPreview:
    desired_users: tuple[RuntimeUser, ...]
    create_ids: tuple[str, ...]
    update_ids: tuple[str, ...]
    disable_ids: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.create_ids or self.update_ids or self.disable_ids)


class UsersReconstructionWorkflow:
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        memberships: ToolMembershipStore,
        profiles: UsersProfileCatalogProvider,
        runtime: UsersRuntimeStore,
        writer: UsersBaseRuntimeWriter,
    ) -> None:
        self._registry = registry
        self._memberships = memberships
        self._profiles = profiles
        self._runtime = runtime
        self._writer = writer

    def inspect(self) -> UsersReconstructionPreview:
        registry = self._registry.load()
        memberships = self._memberships.load()
        profiles = resolve_profile_catalog(self._profiles)
        existing = {user.user_id: user for user in self._runtime.list_users()}
        desired: list[RuntimeUser] = []
        created: list[str] = []
        updated: list[str] = []

        for membership in memberships.memberships:
            identity = registry.get(membership.user_id)
            if identity is None:
                raise UsersReconstructionConflictError('Membership has no durable user identity')
            profile = require_managed_profile(membership.profile_key, profiles=profiles)
            user = build_runtime_user(identity=identity, membership=membership, profile=profile)
            desired.append(user)
            current = existing.get(user.user_id)
            if current is None:
                created.append(user.user_id)
            elif not _same_base(current, user):
                updated.append(user.user_id)

        desired_ids = {user.user_id for user in desired}
        disabled = [
            user.user_id
            for user in existing.values()
            if user.user_id not in desired_ids
            and user.enabled
            and not user.is_local
            and user.profile.id != GUEST_PROFILE_KEY
        ]
        return UsersReconstructionPreview(
            desired_users=tuple(sorted(desired, key=lambda user: user.user_id)),
            create_ids=tuple(sorted(created)),
            update_ids=tuple(sorted(updated)),
            disable_ids=tuple(sorted(disabled)),
        )

    def apply(self, preview: UsersReconstructionPreview) -> UsersReconstructionPreview:
        if not isinstance(preview, UsersReconstructionPreview):
            raise TypeError('Users reconstruction preview is required')
        if self.inspect() != preview:
            raise UsersReconstructionConflictError('Users reconstruction preview changed')

        current = {user.user_id: user for user in self._runtime.list_users()}
        desired = {user.user_id: user for user in preview.desired_users}
        for user_id in preview.disable_ids:
            self._publish(replace(current[user_id], enabled=False))
        for user_id in (*preview.create_ids, *preview.update_ids):
            self._publish(desired[user_id])

        after = self.inspect()
        if after.has_changes:
            raise UsersReconstructionConflictError('Users runtime reconstruction is incomplete')
        return after

    def _publish(self, desired: RuntimeUser) -> None:
        persisted = self._writer.upsert_base_user(desired)
        if not isinstance(persisted, RuntimeUser) or not _same_base(persisted, desired):
            raise UsersReconstructionConflictError('Published Users base does not match source')


def _same_base(left: RuntimeUser, right: RuntimeUser) -> bool:
    return (
        left.identity == right.identity
        and left.enabled == right.enabled
        and left.profile == right.profile
    )
