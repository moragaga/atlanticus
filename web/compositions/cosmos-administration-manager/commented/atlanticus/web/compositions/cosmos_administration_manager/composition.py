from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.compositions.cosmos_administration_manager.entry import (
    create_cosmos_inventory_manager_entry,
)
from atlanticus.web.compositions.deployment_access_manager import (
    DeploymentRootSession,
    compose_root_manager_principal,
    create_deployment_access_manager_entry,
)
from atlanticus.web.cosmos_administration import CosmosAdministrationService
from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurface,
    ManagerSurfaceDefinition,
)


# La composición ensambla contratos ya existentes; no implementa operaciones Cosmos.
def create_cosmos_root_manager_surface(
    *,
    root_session: DeploymentRootSession,
    administration: CosmosAdministrationService,
    fallback_principal: Callable[[], ManagerPrincipal],
    max_items: int = 200,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> ManagerSurface:
    # ROOT comparte proveedor de identidad para ambas entradas administrativas.
    principal = compose_root_manager_principal(
        root_session=root_session, fallback=fallback_principal
    )
    # La política debe ser la misma para el menú y para los callbacks de cada entrada.
    policy = authorization if authorization is not None else DefaultManagerAuthorizationPolicy()
    deployment = create_deployment_access_manager_entry(
        root_session=root_session,
        principal_provider=principal,
        group_key='administration',
        authorization=policy,
    )
    cosmos = create_cosmos_inventory_manager_entry(
        administration=administration,
        root_session=root_session,
        principal_provider=principal,
        group_key='administration',
        max_items=max_items,
        authorization=policy,
    )
    # La frontera HTTP y de callbacks la instalará RootManagerRequestScope el consumidor.
    return ManagerSurface(
        ManagerSurfaceDefinition(
            principal_provider=principal,
            groups=(ManagerModuleGroup(key='administration', title='Administración', order=0),),
            modules=(),
            entries=(deployment, cosmos),
            route_prefix='/manager',
            header_title='Atlanticus ROOT Administration',
        ),
        authorization=policy,
    )
