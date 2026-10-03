from __future__ import annotations

# ManagerPrincipal se deriva del RuntimeUser materializado; no hace joins adicionales.

from dataclasses import dataclass

from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.wiring import (
    ConfigurationManagerStores,
    compose_configuration_manager_dependencies,
)
from atlanticus.connectivity.cosmos import CosmosOperationError
from atlanticus.web.configuration import WebEnvironment, WebSettings
from atlanticus.web.identity.access import AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.profiles.models import LOCAL_PROFILE, LOCAL_PROFILE_KEY, ROOT_PROFILE_KEY
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_USERS
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, build_avatar_text
from atlanticus.web.users.runtime import UsersRuntime


def resolve_manager_principal(
    *,
    access: AccessSnapshot,
    user: RuntimeUser | None,
) -> ManagerPrincipal:
    if not isinstance(access, AccessSnapshot):
        raise TypeError('Manager principal requires an access snapshot')
    if access.status is not AccessStatus.READY or access.identity is None:
        raise ValueError('Manager principal requires ready authenticated access')
    if user is not None and not isinstance(user, RuntimeUser):
        raise TypeError('Manager user must be a RuntimeUser')
    if access.bootstrap_root and user is not None:
        raise ValueError('Bootstrap root cannot use a managed user snapshot')
    if user is not None:
        if user.subject_id != access.identity.subject_id:
            raise ValueError('Manager user does not match authenticated identity')
        if not user.enabled:
            raise ValueError('Disabled user cannot resolve Manager principal')

    profile = None if user is None else user.profile
    is_local = (
        user is not None
        and user.issuer == LOCAL_ISSUER
        and user.profile.id == LOCAL_PROFILE_KEY
    )
    return ManagerPrincipal(
        subject_id=access.identity.subject_id,
        display_name=(
            user.display_name
            if user is not None
            else access.identity.display_name or access.identity.subject_id
        ),
        profile_keys=(() if profile is None else (profile.id,)),
        access_keys=(),
        administrative_override=(
            user is not None and not is_local and user.profile.id == ROOT_PROFILE_KEY
        ),
        is_local=is_local,
        profile_label=None if profile is None else profile.label,
        profile_background_color=None if profile is None else profile.background_color,
        profile_text_color=None if profile is None else profile.text_color,
        avatar_text=None if user is None else build_avatar_text(user.display_name),
    )


@dataclass(frozen=True, slots=True)
class ManagerPrincipalBinding:
    access_runtime: AccessRuntime
    users_runtime: UsersRuntime
    trusted_local_users: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.access_runtime, AccessRuntime):
            raise TypeError('Manager access runtime must be AccessRuntime')
        if not isinstance(self.users_runtime, UsersRuntime):
            raise TypeError('Manager users runtime must be UsersRuntime')
        if not isinstance(self.trusted_local_users, bool):
            raise TypeError('Manager trusted local users flag must be boolean')

    def __call__(self) -> ManagerPrincipal:
        access = self.access_runtime.current()
        user = self.users_runtime.current_or_none(access)
        if self.trusted_local_users and (
            user is None
            or (
                user.issuer == LOCAL_ISSUER
                and user.profile.id == LOCAL_PROFILE_KEY
                and user.enabled
                and access.identity is not None
                and user.subject_id == access.identity.subject_id
            )
        ):
            local = _resolve_trusted_local_principal(access)
            if local is not None:
                return local
        return resolve_manager_principal(access=access, user=user)


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

    principal = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        trusted_local_users=trusted_local_users and resolved_environment.is_local,
    )
    return compose_configuration_manager_dependencies(
        stores=stores,
        principal_provider=principal,
        projection_unavailable_causes=(CosmosOperationError,),
        source_name=source_name,
        projection_name=projection_name,
    )


def _resolve_trusted_local_principal(access: AccessSnapshot) -> ManagerPrincipal | None:
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
    profile = RuntimeProfile.from_profile(LOCAL_PROFILE)
    return ManagerPrincipal(
        subject_id=local.subject_id,
        display_name=local.display_name,
        profile_keys=(profile.id,),
        access_keys=(),
        administrative_override=True,
        is_local=True,
        profile_label=profile.label,
        profile_background_color=profile.background_color,
        profile_text_color=profile.text_color,
        avatar_text=build_avatar_text(local.display_name),
    )
