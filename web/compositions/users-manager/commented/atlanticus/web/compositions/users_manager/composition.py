from __future__ import annotations

# La composición separa administración de usuarios y reconstrucción base del runtime.

from collections.abc import Callable
from dataclasses import dataclass, replace

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
    ManagerEntry,
    ManagerPrincipal,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.reconstruction import UsersReconstructionWorkflow
from atlanticus.web.users.web.reconstruction import (
    UsersReconstructionWebContext,
    build_users_reconstruction_configuration,
    create_users_reconstruction_web_module,
)
from atlanticus.web.users.web import (
    UsersAdminWebContext,
    build_users_admin_configuration,
    create_users_admin_web_module,
)

USERS_ADMINISTRATION_SERVICE = 'users.administration'
UsersPrincipalProvider = Callable[[], ManagerPrincipal]


@dataclass(frozen=True, slots=True)
class UsersManagerComposition:
    entry: ManagerEntry
    administration: UsersAdministrationService


def compose_users_manager(
    *,
    administration: UsersAdministrationService,
    principal_provider: UsersPrincipalProvider,
    group_key: str,
    module_key: str = 'users',
    route: str = '/users',
    order: int = 10,
    title: str = 'Users',
    access_key: str | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> UsersManagerComposition:
    resolved_authorization = authorization or DefaultManagerAuthorizationPolicy()
    context = UsersAdminWebContext(
        administration=administration,
        can_manage=lambda: resolved_authorization.can_view(principal_provider(), entry),
    )

    def layout(_services: ServiceRegistry) -> object:
        return build_users_admin_configuration(context)

    web_module = create_users_admin_web_module(context)

    def register_services(services: ServiceRegistry) -> None:
        services.add(USERS_ADMINISTRATION_SERVICE, administration)

    entry = ManagerEntry(
        key=module_key,
        group_key=group_key,
        title=title,
        route=route,
        order=order,
        description='Identidad global y membership de usuarios para esta Tool.',
        layout=layout,
        access_key=access_key,
        web_module=replace(web_module, register_services=register_services),
    )
    return UsersManagerComposition(entry=entry, administration=administration)


def compose_users_reconstruction_manager(
    *,
    reconstruction: UsersReconstructionWorkflow,
    principal_provider: UsersPrincipalProvider,
    group_key: str,
    access_key: str,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> ManagerEntry:
    policy = authorization or DefaultManagerAuthorizationPolicy()
    context = UsersReconstructionWebContext(
        workflow=reconstruction,
        can_manage=lambda: policy.can_view(principal_provider(), entry),
    )
    entry = ManagerEntry(
        key='users-projection',
        group_key=group_key,
        title='Reconstrucción de usuarios',
        route='/users-projection',
        order=11,
        description='Reconstrucción controlada desde Registry, Memberships y Profiles vigentes.',
        layout=lambda _services: build_users_reconstruction_configuration(context),
        access_key=access_key,
        web_module=create_users_reconstruction_web_module(context),
    )
    return entry
