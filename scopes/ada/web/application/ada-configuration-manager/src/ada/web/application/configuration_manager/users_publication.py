from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from atlanticus.web.users.administration import (
    RuntimePublicationStatus,
    UsersAdministrationService,
    UsersAdministrationSnapshot,
)
from atlanticus.web.users.errors import UserPromotionError
from atlanticus.web.users.models import ManagedUser, RuntimeUser
from atlanticus.web.users.profiles import UsersProfileCatalogProvider
from atlanticus.web.users.reconstruction import UsersReconstructionPreview
from atlanticus.web.users.store import (
    ToolMembershipStore,
    UsersDirectoryReader,
    UsersGuestReader,
    UsersRegistryStore,
)


_LOGGER = logging.getLogger(__name__)


class UsersRuntimePublicationPendingError(RuntimeError):
    pass


class AdaUsersAdministrationService(UsersAdministrationService):
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        memberships: ToolMembershipStore,
        profiles: UsersProfileCatalogProvider,
        directory: UsersDirectoryReader | None = None,
        guest_reader: UsersGuestReader | None = None,
        publish_runtime: Callable[[str], RuntimeUser],
        inspect_runtime: Callable[[], UsersReconstructionPreview] | None = None,
    ) -> None:
        super().__init__(
            registry=registry,
            memberships=memberships,
            profiles=profiles,
            directory=directory,
            guest_reader=guest_reader,
        )
        if not callable(publish_runtime):
            raise TypeError('Users runtime publisher must be callable')
        if inspect_runtime is not None and not callable(inspect_runtime):
            raise TypeError('Users runtime inspector must be callable')
        self._publish_runtime = publish_runtime
        self._inspect_runtime = inspect_runtime

    def discover(self) -> UsersAdministrationSnapshot:
        snapshot = super().discover()
        if self._inspect_runtime is None:
            return snapshot
        try:
            preview = self._inspect_runtime()
            if not isinstance(preview, UsersReconstructionPreview):
                raise TypeError('Users runtime inspector returned an invalid preview')
            create = set(preview.create_ids)
            update = set(preview.update_ids)
            desired = {user.user_id for user in preview.desired_users}

            def status(user_id: str) -> RuntimePublicationStatus:
                if user_id in create:
                    return RuntimePublicationStatus.MISSING
                if user_id in update:
                    return RuntimePublicationStatus.OUTDATED
                if user_id in desired:
                    return RuntimePublicationStatus.SYNCHRONIZED
                return RuntimePublicationStatus.UNAVAILABLE

        except Exception as error:
            _LOGGER.warning('Users runtime inspection unavailable (%s)', type(error).__name__)

            def status(user_id: str) -> RuntimePublicationStatus:
                del user_id
                return RuntimePublicationStatus.UNAVAILABLE

        return replace(
            snapshot,
            candidates=tuple(
                replace(candidate, runtime_status=status(candidate.user_id))
                if candidate.promoted_user is not None else candidate
                for candidate in snapshot.candidates
            ),
        )

    def promote(
        self,
        user_id: str,
        *,
        profile_key: str,
        enabled: bool = True,
        expected_registry_version: str | None,
        expected_membership_version: str | None,
    ) -> ManagedUser:
        managed = super().promote(
            user_id,
            profile_key=profile_key,
            enabled=enabled,
            expected_registry_version=expected_registry_version,
            expected_membership_version=expected_membership_version,
        )
        self._publish(managed.user_id)
        return managed

    def update(
        self,
        user_id: str,
        *,
        profile_key: str,
        enabled: bool,
        expected_registry_version: str | None = None,
        expected_membership_version: str | None,
    ) -> ManagedUser:
        managed = super().update(
            user_id,
            profile_key=profile_key,
            enabled=enabled,
            expected_registry_version=expected_registry_version,
            expected_membership_version=expected_membership_version,
        )
        self._publish(managed.user_id)
        return managed

    def retry_runtime(self, user_id: str) -> RuntimeUser:
        if not any(user.user_id == user_id for user in self.managed_users()):
            raise UserPromotionError('User does not have a managed Tool membership')
        return self._publish(user_id)

    def _publish(self, user_id: str) -> RuntimeUser:
        try:
            published = self._publish_runtime(user_id)
            if not isinstance(published, RuntimeUser) or published.user_id != user_id:
                raise ValueError('Users runtime publisher returned a different user')
            return published
        except Exception as error:
            raise UsersRuntimePublicationPendingError(
                'Tool membership was saved but users-runtime publication is pending. '
                'Refresh Users and save the user again to retry.'
            ) from error
