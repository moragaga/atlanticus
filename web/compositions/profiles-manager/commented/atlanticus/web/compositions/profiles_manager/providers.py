from __future__ import annotations

from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.compositions.profiles_manager.composition import (
    ProfilesManagerComposition,
    ProfilesPrincipalProvider,
    compose_profiles_manager,
)
from atlanticus.web.compositions.profiles_manager.workflows import ProfilesAuditActorProvider
from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.profiles.projection.cosmos import (
    CosmosProfilesProjectionStore,
    CosmosProfilesProjectionStoreSettings,
)
from atlanticus.web.profiles.projection.local import (
    LocalProfilesProjectionStore,
    LocalProfilesProjectionStoreSettings,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


# Provider local: filesystem durable para Source y archivo local para Projection.
def compose_local_profiles_manager(
    *,
    services: ServiceRegistry,
    source_settings: LocalSourceSettings,
    projection_settings: LocalProfilesProjectionStoreSettings,
    principal_provider: ProfilesPrincipalProvider,
    group_key: str,
    module_key: str = 'profiles',
    route: str = '/profiles',
    order: int = 10,
    access_key: str | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: ProfilesAuditActorProvider | None = None,
) -> ProfilesManagerComposition:
    return compose_profiles_manager(
        services=services,
        source_store=LocalSourceStore(source_settings),
        projection_store=LocalProfilesProjectionStore(projection_settings),
        principal_provider=principal_provider,
        group_key=group_key,
        module_key=module_key,
        route=route,
        order=order,
        access_key=access_key,
        authorization=authorization,
        audit_actor_provider=audit_actor_provider,
    )


# Provider Azure: Blob sigue siendo Source durable y Cosmos sirve la Projection activa.
def compose_azure_profiles_manager(
    *,
    services: ServiceRegistry,
    storage: StorageClient,
    source_settings: BlobSourceSettings,
    cosmos: CosmosClient,
    projection_settings: CosmosProfilesProjectionStoreSettings,
    principal_provider: ProfilesPrincipalProvider,
    group_key: str,
    module_key: str = 'profiles',
    route: str = '/profiles',
    order: int = 10,
    access_key: str | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: ProfilesAuditActorProvider | None = None,
) -> ProfilesManagerComposition:
    return compose_profiles_manager(
        services=services,
        source_store=BlobSourceStore(source_settings, storage=storage),
        projection_store=CosmosProfilesProjectionStore(
            client=cosmos,
            settings=projection_settings,
        ),
        principal_provider=principal_provider,
        group_key=group_key,
        module_key=module_key,
        route=route,
        order=order,
        access_key=access_key,
        authorization=authorization,
        audit_actor_provider=audit_actor_provider,
    )
