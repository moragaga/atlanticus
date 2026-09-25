from __future__ import annotations

import logging
from dataclasses import replace

from ada.web.application.configuration_manager.composition import (
    MANAGER_ROUTE_PREFIX,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.pages import __name__ as _manager_pages_package
from ada.web.application.configuration_manager.wiring import (
    ConfigurationManagerStores,
    read_manager_projection,
)
from ada.web.application.generic.manager_integration import integrate_manager_surface
from ada.web.application.generic.manager_principal import compose_integrated_manager_dependencies
from ada.web.application.generic.operational_collector import attach_operational_kpi_collector
from ada.web.application.generic.operational_tool import (
    create_definition_from_tool_resolution,
    resolve_operational_tool_projection,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.tools.persistence import (
    ToolProjectionResolution,
    ToolProjectionResolutionState,
    compose_tool_persistence,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError, CosmosOperationError
from atlanticus.connectivity.storage import (
    StorageAuthenticationError,
    StorageAuthorizationError,
    StorageClient,
    StorageConnectionError,
    StorageContainerNotFoundError,
    StorageError,
    StorageOperationError,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.configuration import WebSettings
from atlanticus.web.identity.access import (
    AccessResolver,
    AccessRuntime,
    AuthenticatedAccessResolver,
)
from atlanticus.web.identity.errors import IdentityConfigurationError
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerSurface
from atlanticus.web.manager.web.ids import LOCATION_ID
from atlanticus.web.models import WebApplicationDefinition, WebApplicationRuntime
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.source.errors import SourceUnavailableError
from atlanticus.web.users.errors import UsersStoreUnavailableError
from atlanticus.web.users.module import create_users_module
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore

_LOGGER = logging.getLogger(__name__)
# Excepciones de infraestructura que degradan solamente la vista administrativa.
_MANAGER_UNAVAILABLE_ERRORS = (
    CosmosOperationError,
    StorageAuthenticationError,
    StorageAuthorizationError,
    StorageConnectionError,
    StorageContainerNotFoundError,
    StorageOperationError,
    ProjectionStoreError,
    SourceUnavailableError,
    UsersStoreUnavailableError,
)


# El arranque de ADA y del Collector conserva su ciclo de vida actual.
def create_operational_application_runtime(
    *,
    settings: AdaGenericSettings | None = None,
    manager_dependencies: ConfigurationManagerDependencies | None = None,
    manager_stores: ConfigurationManagerStores | None = None,
    identity_provider: IdentityProvider | None = None,
) -> WebApplicationRuntime:
    if settings is not None and not isinstance(settings, AdaGenericSettings):
        raise TypeError('settings must be AdaGenericSettings')
    if manager_dependencies is not None and not isinstance(
        manager_dependencies, ConfigurationManagerDependencies
    ):
        raise TypeError('manager_dependencies must be ConfigurationManagerDependencies')

    if manager_stores is not None and not isinstance(manager_stores, ConfigurationManagerStores):
        raise TypeError('manager_stores must be ConfigurationManagerStores')
    if identity_provider is not None and not isinstance(identity_provider, IdentityProvider):
        raise TypeError('identity_provider must implement IdentityProvider')
    if manager_dependencies is not None and manager_stores is not None:
        raise ValueError('Use manager_stores or manager_dependencies, not both')
    if identity_provider is not None and manager_stores is None:
        raise ValueError('identity_provider requires manager_stores')

    resolved_settings = settings or AdaGenericSettings()
    manager_identity = None
    if manager_stores is not None:
        manager_identity = _prepare_manager_identity(
            stores=manager_stores,
            provider=identity_provider,
            settings=resolved_settings,
        )
        manager_dependencies = manager_identity[2]
    resolution = _resolve_tool_projection(resolved_settings)
    definition = create_definition_from_tool_resolution(resolution)
    if manager_identity is not None:
        provider, users_runtime, _dependencies, resolver = manager_identity
        definition = _bind_manager_identity(definition, provider, users_runtime, resolver)
    kpi_cosmos_client = None

    try:
        if resolution.state is ToolProjectionResolutionState.READY:
            projection = resolution.projection
            if projection is None:
                raise RuntimeError('READY Tool Projection resolution has no projection')
            kpi_cosmos_settings = resolved_settings.kpi_delivery_cosmos_settings()
            if kpi_cosmos_settings is None:
                _LOGGER.info('KPI Collector is not configured')
            else:
                kpi_cosmos_client = CosmosClient(settings=kpi_cosmos_settings)
                definition = attach_operational_kpi_collector(
                    definition,
                    tool_projection=projection,
                    cosmos_client=kpi_cosmos_client,
                    reader_settings=resolved_settings.kpi_delivery_reader_settings(),
                )

        if manager_dependencies is not None:
            definition = _integrate_manager(definition, manager_dependencies)

        return create_web_application(definition)
    except Exception:
        _close_client(kpi_cosmos_client, 'KPI Delivery Cosmos')
        raise


# El composition root decide qué fallas son recuperables; el núcleo Web es neutral.
# Prepara identidad y dependencias una sola vez, antes de construir la aplicación.
# La misma instancia de UsersRuntime alimenta autorización del Manager y bootstrap de acceso.
def _prepare_manager_identity(
    *,
    stores: ConfigurationManagerStores,
    provider: IdentityProvider | None,
    settings: AdaGenericSettings,
) -> tuple[IdentityProvider, UsersRuntime, ConfigurationManagerDependencies, AccessResolver]:
    if WebSettings().environment is not settings.environment:
        raise ValueError('Integrated Manager environment does not match Web environment')
    resolved_provider = provider or LocalIdentityProvider()
    if settings.environment.is_production and not resolved_provider.production_ready:
        raise IdentityConfigurationError('Production Manager requires a production identity provider')
    shared_store = (
        stores.users_promoted if isinstance(stores.users_promoted, UsersRuntimeStore) else None
    )
    if shared_store is None and not isinstance(resolved_provider, LocalIdentityProvider):
        raise ValueError('Non-local Manager identity requires a shared Users runtime store')
    if shared_store is None and settings.environment.is_production:
        raise ValueError('Production Manager requires a shared Users runtime store')

    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    dependencies = compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        environment=settings.environment,
    )
    if shared_store is None:
        resolver = AuthenticatedAccessResolver()
    else:
        def profiles_provider() -> ProfileCatalog:
            try:
                active = read_manager_projection(
                    stores.profiles,
                    PROFILES_CONFIGURATION_SOURCE_KEY,
                    ProfileCatalog,
                    unavailable_causes=(CosmosOperationError,),
                )
            except ProjectionStoreError as error:
                raise UsersStoreUnavailableError('Users profiles projection is unavailable') from error
            return active if active is not None else ProfileCatalog()

        resolver = UsersAccessResolver(
            store=shared_store,
            runtime=users_runtime,
            profiles=profiles_provider,
        )
    return resolved_provider, users_runtime, dependencies, resolver


# Sustituye la identidad local por la identidad explícita en el composition root.
# El módulo Users comparte con el resolver el mismo runtime de sesión por request.
def _bind_manager_identity(
    definition: WebApplicationDefinition,
    provider: IdentityProvider,
    users_runtime: UsersRuntime,
    resolver: AccessResolver,
) -> WebApplicationDefinition:
    identity = create_identity_module(provider, access_resolver=resolver)
    if sum(module.name == identity.name for module in definition.modules) != 1:
        raise ValueError('Operational definition must contain exactly one identity module')
    if any(module.name == 'users' for module in definition.modules):
        raise ValueError('Operational definition already registers Users runtime')
    return replace(
        definition,
        modules=(
            *(identity if module.name == identity.name else module for module in definition.modules),
            create_users_module(users_runtime),
        ),
    )


def _integrate_manager(
    definition: WebApplicationDefinition,
    dependencies: ConfigurationManagerDependencies,
) -> WebApplicationDefinition:
    surface = ManagerSurface(build_configuration_manager_surface(dependencies))
    return integrate_manager_surface(
        definition,
        manager=surface,
        page_packages=(_manager_pages_package,),
        route_prefix=MANAGER_ROUTE_PREFIX,
        location_id=LOCATION_ID,
        # Errores de validación/programación no se incluyen para evitar ocultarlos.
        unavailable_errors=_MANAGER_UNAVAILABLE_ERRORS,
    )


# Las conexiones transitorias de Tool se cierran al terminar la resolución.
def _resolve_tool_projection(settings: AdaGenericSettings) -> ToolProjectionResolution:
    storage_client = _create_storage_client(settings)
    cosmos_client = _create_tool_projection_cosmos_client(settings)
    try:
        persistence = compose_tool_persistence(
            settings=settings.tool_persistence_settings(),
            storage_client=storage_client,
            cosmos_client=cosmos_client,
        )
        return resolve_operational_tool_projection(persistence)
    finally:
        _close_client(storage_client, 'Storage')
        _close_client(cosmos_client, 'Tool Projection Cosmos')


def _create_storage_client(settings: AdaGenericSettings) -> StorageClient | None:
    storage_settings = settings.storage_settings()
    if storage_settings is None:
        return None
    return StorageClient(settings=storage_settings)


def _create_tool_projection_cosmos_client(
    settings: AdaGenericSettings,
) -> CosmosClient | None:
    cosmos_settings = settings.tool_projection_cosmos_settings()
    if cosmos_settings is None:
        return None
    return CosmosClient(settings=cosmos_settings)


# Se intenta cerrar siempre el cliente antes de devolver o propagar.
def _close_client(client: StorageClient | CosmosClient | None, provider_name: str) -> None:
    if client is None:
        return
    try:
        client.close()
    except (StorageError, CosmosError) as error:
        _LOGGER.warning('Could not close %s client: %s', provider_name, error)
