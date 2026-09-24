from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada.web.access.configuration import AdaAccessConfiguration
from atlanticus.web.identity.access import AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


# Convierte identidad y perfiles efectivos en permisos explicitos de Manager.
# Sin proyecciones o sin usuario promovido, la resolucion no concede permisos.
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


# Adapta los snapshots ligados a la solicitud y proveedores de proyecciones.
# Los proveedores son explicitos para evitar un cliente Cosmos global.
@dataclass(frozen=True, slots=True)
class ManagerPrincipalBinding:
    access_runtime: AccessRuntime
    users_runtime: UsersRuntime
    configuration_provider: Callable[[], AdaAccessConfiguration | None]
    profiles_provider: Callable[[], ProfileCatalog | None]

    def __post_init__(self) -> None:
        if not isinstance(self.access_runtime, AccessRuntime):
            raise TypeError('Manager access runtime must be AccessRuntime')
        if not isinstance(self.users_runtime, UsersRuntime):
            raise TypeError('Manager users runtime must be UsersRuntime')
        if not callable(self.configuration_provider):
            raise TypeError('Manager configuration provider must be callable')
        if not callable(self.profiles_provider):
            raise TypeError('Manager profiles provider must be callable')

    def __call__(self) -> ManagerPrincipal:
        access = self.access_runtime.current()
        user = self.users_runtime.current_or_none(access)
        return resolve_manager_principal(
            access=access,
            user=user,
            configuration=(self.configuration_provider() if user is not None else None),
            profiles=(self.profiles_provider() if user is not None else None),
        )
