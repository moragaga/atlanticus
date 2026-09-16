from __future__ import annotations

from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.compositions.navigation_manager.composition import (
    NavigationManagerComposition,
    NavigationPrincipalProvider,
    NavigationProfileOptionsProvider,
    compose_navigation_manager,
)
from atlanticus.web.compositions.navigation_manager.workflows import (
    NavigationAuditActorProvider,
)
from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.models import ManagerModuleAccess
from atlanticus.web.navigation.configuration.source_projection import NavigationProjectionValidator
from atlanticus.web.navigation.projection.cosmos import (
    CosmosNavigationProjectionStore,
    CosmosNavigationProjectionStoreSettings,
)
from atlanticus.web.navigation.projection.local import (
    LocalNavigationProjectionStore,
    LocalNavigationProjectionStoreSettings,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def compose_local_navigation_manager(
    *,
    services: ServiceRegistry,
    source_settings: LocalSourceSettings,
    projection_settings: LocalNavigationProjectionStoreSettings,
    principal_provider: NavigationPrincipalProvider,
    group_key: str,
    module_key: str = 'navigation',
    route: str = '/navigation',
    order: int = 20,
    access: ManagerModuleAccess | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: NavigationAuditActorProvider | None = None,
    profile_options_provider: NavigationProfileOptionsProvider | None = None,
    projection_validators: tuple[NavigationProjectionValidator, ...] = (),
) -> NavigationManagerComposition:
    return compose_navigation_manager(
        services=services,
        source_store=LocalSourceStore(source_settings),
        projection_store=LocalNavigationProjectionStore(projection_settings),
        principal_provider=principal_provider,
        group_key=group_key,
        module_key=module_key,
        route=route,
        order=order,
        access=access,
        authorization=authorization,
        audit_actor_provider=audit_actor_provider,
        profile_options_provider=profile_options_provider,
        projection_validators=projection_validators,
    )


def compose_azure_navigation_manager(
    *,
    services: ServiceRegistry,
    storage: StorageClient,
    source_settings: BlobSourceSettings,
    cosmos: CosmosClient,
    projection_settings: CosmosNavigationProjectionStoreSettings,
    principal_provider: NavigationPrincipalProvider,
    group_key: str,
    module_key: str = 'navigation',
    route: str = '/navigation',
    order: int = 20,
    access: ManagerModuleAccess | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: NavigationAuditActorProvider | None = None,
    profile_options_provider: NavigationProfileOptionsProvider | None = None,
    projection_validators: tuple[NavigationProjectionValidator, ...] = (),
) -> NavigationManagerComposition:
    return compose_navigation_manager(
        services=services,
        source_store=BlobSourceStore(source_settings, storage=storage),
        projection_store=CosmosNavigationProjectionStore(
            client=cosmos,
            settings=projection_settings,
        ),
        principal_provider=principal_provider,
        group_key=group_key,
        module_key=module_key,
        route=route,
        order=order,
        access=access,
        authorization=authorization,
        audit_actor_provider=audit_actor_provider,
        profile_options_provider=profile_options_provider,
        projection_validators=projection_validators,
    )
