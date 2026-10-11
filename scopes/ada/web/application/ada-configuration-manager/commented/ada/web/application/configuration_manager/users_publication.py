from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.errors import UserPromotionError
from atlanticus.web.users.models import ManagedUser, RuntimeUser
from atlanticus.web.users.profiles import UsersProfileCatalogProvider
from atlanticus.web.users.store import (
    ToolMembershipStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)


class UsersRuntimePublicationPendingError(RuntimeError):
    pass


# Adaptador de ADA: primero conserva Source y después publica un RuntimeUser individual.
class AdaUsersAdministrationService(UsersAdministrationService):
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        memberships: ToolMembershipStore,
        profiles: UsersProfileCatalogProvider,
        directory: UsersDirectoryReader | None = None,
        publish_runtime: Callable[[str], RuntimeUser],
    ) -> None:
        super().__init__(
            registry=registry,
            memberships=memberships,
            profiles=profiles,
            directory=directory,
        )
        if not callable(publish_runtime):
            raise TypeError('Users runtime publisher must be callable')
        self._publish_runtime = publish_runtime

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

    # Reintenta exclusivamente Runtime sin crear una nueva revisión de membership.
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
