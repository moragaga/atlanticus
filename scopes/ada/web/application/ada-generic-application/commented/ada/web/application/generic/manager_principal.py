from __future__ import annotations

# Extrae permisos desde snapshots y proyecciones compartidas por la aplicación.
# Declara aquí el error físico recuperable, en lugar de acoplar el Manager neutral a Cosmos.
# La concesión local enumera claves sólo para Jane y John con identidad confiable.

from collections.abc import Callable
from dataclasses import dataclass

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.wiring import (
    ADA_ACCESS_SOURCE_KEY,
    MANAGER_ACCESS_KEYS,
    ConfigurationManagerStores,
    compose_configuration_manager_dependencies,
    read_manager_projection,
)
from atlanticus.connectivity.cosmos import CosmosOperationError
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.configuration import WebEnvironment, WebSettings
from atlanticus.web.identity.access import AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY, ProfileCatalog
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_USERS
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


# Composición o lectura independiente del proveedor físico.
def resolve_manager_principal(
    *,
    access: AccessSnapshot,
    user: EffectiveUser | None,
    configuration: AdaAccessConfiguration | None,
    profiles: ProfileCatalog | None,
) -> ManagerPrincipal:
    if not isinstance(access, AccessSnapshot):
        raise TypeError('Manager principal requires an access snapshot')
    if access.status is not AccessStatus.READY or access.identity is None:
        raise ValueError('Manager principal requires ready authenticated access')
    if user is not None and not isinstance(user, EffectiveUser):
        raise TypeError('Manager user must be an EffectiveUser')
    if configuration is not None and not isinstance(configuration, AdaAccessConfiguration):
        raise TypeError('Manager access configuration is invalid')
    if profiles is not None and not isinstance(profiles, ProfileCatalog):
        raise TypeError('Manager profile catalog is invalid')
    if access.bootstrap_root and user is not None:
        raise ValueError('Bootstrap root cannot use a managed user snapshot')
    if user is not None:
        if user.subject_id != access.identity.subject_id:
            raise ValueError('Manager user does not match authenticated identity')
        if not user.enabled:
            raise ValueError('Disabled user cannot resolve Manager principal')

    granted: tuple[str, ...] = ()
    if user is not None and configuration is not None and profiles is not None:
        granted = configuration.resolve(user.profile_key, profiles=profiles).access_keys

    return ManagerPrincipal(
        subject_id=access.identity.subject_id,
        display_name=(
            user.display_name
            if user is not None
            else access.identity.display_name or access.identity.subject_id
        ),
        profile_keys=(() if user is None else (user.profile_key,)),
        access_keys=granted,
        is_local=(user.is_local if user is not None else False),
    )


@dataclass(frozen=True, slots=True)
# Contrato de estado de la frontera.
class ManagerPrincipalBinding:
    access_runtime: AccessRuntime
    users_runtime: UsersRuntime
    configuration_provider: Callable[[], AdaAccessConfiguration | None]
    profiles_provider: Callable[[], ProfileCatalog | None]
    trusted_local_users: bool = False

    # Verifica invariantes y deriva datos de la entrada explícita.
    def __post_init__(self) -> None:
        if not isinstance(self.access_runtime, AccessRuntime):
            raise TypeError('Manager access runtime must be AccessRuntime')
        if not isinstance(self.users_runtime, UsersRuntime):
            raise TypeError('Manager users runtime must be UsersRuntime')
        if not callable(self.configuration_provider):
            raise TypeError('Manager configuration provider must be callable')
        if not callable(self.profiles_provider):
            raise TypeError('Manager profiles provider must be callable')
        if not isinstance(self.trusted_local_users, bool):
            raise TypeError('Manager trusted local users flag must be boolean')

    # Verifica invariantes y deriva datos de la entrada explícita.
    def __call__(self) -> ManagerPrincipal:
        access = self.access_runtime.current()
        user = self.users_runtime.current_or_none(access)
        if self.trusted_local_users and (
            user is None
            or (
                user.is_local
                and user.enabled
                and access.identity is not None
                and user.subject_id == access.identity.subject_id
            )
        ):
            local = _resolve_trusted_local_principal(access)
            if local is not None:
                return local
        return resolve_manager_principal(
            access=access,
            user=user,
            configuration=(self.configuration_provider() if user is not None else None),
            profiles=(self.profiles_provider() if user is not None else None),
        )


# Composición o lectura independiente del proveedor físico.
def compose_integrated_manager_dependencies(
    *,
    stores: ConfigurationManagerStores,
    access_runtime: AccessRuntime,
    users_runtime: UsersRuntime,
    trusted_local_users: bool = True,
    environment: WebEnvironment | None = None,
    source_name: str = 'Source',
    projection_name: str = 'Projection',
) -> ConfigurationManagerDependencies:
    if not isinstance(stores, ConfigurationManagerStores):
        raise TypeError('Integrated Manager stores are invalid')
    resolved_environment = WebSettings().environment if environment is None else environment
    if not isinstance(resolved_environment, WebEnvironment):
        raise TypeError('Integrated Manager environment must be WebEnvironment')

    # Verifica invariantes y deriva datos de la entrada explícita.
    def configuration_provider() -> AdaAccessConfiguration | None:
        return read_manager_projection(
            stores.access,
            ADA_ACCESS_SOURCE_KEY,
            AdaAccessConfiguration,
            unavailable_causes=(CosmosOperationError,),
        )

    # Verifica invariantes y deriva datos de la entrada explícita.
    def profiles_provider() -> ProfileCatalog | None:
        return read_manager_projection(
            stores.profiles,
            PROFILES_CONFIGURATION_SOURCE_KEY,
            ProfileCatalog,
            unavailable_causes=(CosmosOperationError,),
        )

    principal = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        configuration_provider=configuration_provider,
        profiles_provider=profiles_provider,
        trusted_local_users=trusted_local_users and resolved_environment.is_local,
    )
    return compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=principal,
        projection_unavailable_causes=(CosmosOperationError,),
        source_name=source_name,
        projection_name=projection_name,
    )


# Composición o lectura independiente del proveedor físico.
def _resolve_trusted_local_principal(access: AccessSnapshot) -> ManagerPrincipal | None:
    if not WebSettings().environment.is_local:
        return None
    identity = access.identity
    if (
        access.status is not AccessStatus.READY
        or access.bootstrap_root
        or identity is None
        or identity.provider_key != 'local'
        or identity.issuer != LOCAL_ISSUER
    ):
        return None
    local = next((user for user in LOCAL_USERS if user.subject_id == identity.subject_id), None)
    if local is None:
        return None
    return ManagerPrincipal(
        subject_id=local.subject_id,
        display_name=local.display_name,
        profile_keys=(LOCAL_PROFILE_KEY,),
        access_keys=MANAGER_ACCESS_KEYS,
        is_local=True,
    )
