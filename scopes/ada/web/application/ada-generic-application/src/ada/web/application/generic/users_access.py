from __future__ import annotations

from dataclasses import replace

from ada.web.access.configuration import ADA_ACCESS_SOURCE_KEY, AdaAccessConfiguration
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.users.errors import UsersStoreUnavailableError
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore


class AdaInitialUsersStore(UsersRuntimeStore):
    def __init__(
        self,
        *,
        runtime: UsersRuntimeStore,
        profiles: ProjectionStore[ProfileCatalog],
        access: ProjectionStore[AdaAccessConfiguration],
    ) -> None:
        self._runtime = runtime
        self._profiles = profiles
        self._access = access

    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUser | None:
        user = self._runtime.resolve(identity)
        if user is None or not user.enabled:
            return user

        try:
            profile_record = self._profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
            catalog = ProfileCatalog() if profile_record is None else profile_record.payload
            if not isinstance(catalog, ProfileCatalog):
                raise TypeError('ADA profiles projection has an invalid payload')
            profile = RuntimeProfile.from_profile(catalog.require(user.profile.id))

            access_record = self._access.get_active(ADA_ACCESS_SOURCE_KEY)
            keys: tuple[str, ...] = ()
            if access_record is not None:
                if (
                    profile_record is None
                    or access_record.dependencies != (profile_record.target,)
                    or not isinstance(access_record.payload, AdaAccessConfiguration)
                ):
                    raise ValueError('ADA access projection is incompatible with profiles')
                access_record.payload.validate_profiles(catalog)
                keys = tuple(
                    sorted(
                        access_record.payload.resolve(
                            profile.id, profiles=catalog
                        ).access_keys
                    )
                )
            return replace(user, profile=profile, access_keys=keys)
        except Exception as error:
            raise UsersStoreUnavailableError('Could not resolve ADA initial user access') from error

    def list_users(self) -> tuple[RuntimeUser, ...]:
        return self._runtime.list_users()

    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]:
        return self._runtime.replace_all(users)
