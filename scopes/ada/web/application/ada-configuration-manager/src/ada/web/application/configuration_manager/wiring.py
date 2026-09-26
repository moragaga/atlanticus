from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from ada.web.access.configuration import (
    AdaAccessConfiguration,
    AdaAccessSourceService,
    create_ada_access_projection_service,
)
from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.application.configuration_manager.access import ACCESS_MANAGER_ACCESS_KEY
from ada.web.application.configuration_manager.composition import (
    KPI_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.tool_kpi_registry_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.kpis.definition.configuration import (
    KpiDefinitionSourceService,
    create_kpi_definition_projection_service,
)
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.registry.configuration import (
    KpiRegistrySourceService,
    create_kpi_registry_projection_service,
)
from ada.web.kpis.registry.models import KpiRegistry
from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolSourceService,
    create_tool_projection_service,
)
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    compose_profiles_manager,
)
from atlanticus.web.compositions.users_manager import compose_users_manager
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
    create_navigation_projection_service,
)
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.store import (
    UsersAdministrationStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)

NAVIGATION_SOURCE_KEY = SourceKey('navigation')
TOOLS_SOURCE_KEY = SourceKey('tools')
KPI_REGISTRY_SOURCE_KEY = SourceKey('kpis')
KPI_DEFINITION_SOURCE_KEY = SourceKey('kpi-definitions')
ADA_ACCESS_SOURCE_KEY = SourceKey('ada-access')

PayloadT = TypeVar('PayloadT')

MANAGER_ACCESS_KEYS = (
    USERS_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    ACCESS_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
    KPI_MANAGER_ACCESS_KEY,
)


@dataclass(frozen=True, slots=True)
class ConfigurationManagerStores:
    navigation_source: SourceStore
    tools_source: SourceStore
    access_source: SourceStore
    profiles_source: SourceStore
    kpi_registry_source: SourceStore
    kpi_definitions_source: SourceStore
    navigation: ProjectionStore[NavigationConfigurationCatalog]
    tools: ProjectionStore[ToolConfiguration]
    access: ProjectionStore[AdaAccessConfiguration]
    profiles: ProjectionStore[ProfileCatalog]
    kpi_registry: ProjectionStore[KpiRegistry]
    kpi_definitions: ProjectionStore[KpiDefinitionCatalog]
    users_registry: UsersRegistryStore
    users_promoted: UsersAdministrationStore
    users_directory: UsersDirectoryReader | None = None

    def __post_init__(self) -> None:
        for name, expected in (
            ('navigation_source', SourceStore),
            ('tools_source', SourceStore),
            ('access_source', SourceStore),
            ('profiles_source', SourceStore),
            ('kpi_registry_source', SourceStore),
            ('kpi_definitions_source', SourceStore),
            ('navigation', ProjectionStore),
            ('tools', ProjectionStore),
            ('access', ProjectionStore),
            ('profiles', ProjectionStore),
            ('kpi_registry', ProjectionStore),
            ('kpi_definitions', ProjectionStore),
            ('users_registry', UsersRegistryStore),
            ('users_promoted', UsersAdministrationStore),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(
                    f'Configuration Manager {name} must implement {expected.__name__}'
                )
        if self.users_directory is not None and not isinstance(
            self.users_directory, UsersDirectoryReader
        ):
            raise TypeError('Configuration Manager directory must implement UsersDirectoryReader')


def compose_configuration_manager_dependencies(
    *,
    stores: ConfigurationManagerStores,
    principal_provider: Callable[[], ManagerPrincipal],
    projection_unavailable_causes: tuple[type[Exception], ...] = (),
    source_name: str = 'Source',
    projection_name: str = 'Projection',
    profiles_projection_name: str | None = None,
    kpi_projection_name: str | None = None,
) -> ConfigurationManagerDependencies:
    if not isinstance(stores, ConfigurationManagerStores):
        raise TypeError('Configuration Manager stores are invalid')
    if not callable(principal_provider):
        raise TypeError('Configuration Manager principal provider must be callable')

    navigation_source = NavigationSourceService(
        source=stores.navigation_source, source_key=NAVIGATION_SOURCE_KEY
    )
    tools_source = ToolSourceService(source=stores.tools_source, source_key=TOOLS_SOURCE_KEY)
    access_source = AdaAccessSourceService(
        source=stores.access_source, source_key=ADA_ACCESS_SOURCE_KEY
    )
    kpi_registry_source = KpiRegistrySourceService(
        source=stores.kpi_registry_source, source_key=KPI_REGISTRY_SOURCE_KEY
    )
    kpi_definitions_source = KpiDefinitionSourceService(
        source=stores.kpi_definitions_source, source_key=KPI_DEFINITION_SOURCE_KEY
    )

    navigation_projection = create_navigation_projection_service(
        source=stores.navigation_source, projection=stores.navigation
    )
    tools_projection = create_tool_projection_service(
        source=stores.tools_source, projection=stores.tools
    )
    access_projection = create_ada_access_projection_service(
        source=stores.access_source,
        projection=stores.access,
        profiles_projection=stores.profiles,
        profiles_source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
    )
    kpi_destinations = ToolConfigurationKpiDestinationCatalogProvider(
        projection=stores.tools, source_key=TOOLS_SOURCE_KEY
    )
    kpi_registry_projection = create_kpi_registry_projection_service(
        source=stores.kpi_registry_source,
        projection=stores.kpi_registry,
        destinations=kpi_destinations,
    )
    kpi_definitions_projection = create_kpi_definition_projection_service(
        source=stores.kpi_definitions_source,
        projection=stores.kpi_definitions,
        kpi_registry_projection=stores.kpi_registry,
        kpi_registry_source_key=KPI_REGISTRY_SOURCE_KEY,
    )
    profiles_manager = compose_profiles_manager(
        source_store=stores.profiles_source,
        projection_store=stores.profiles,
        principal_provider=principal_provider,
        group_key='configuration',
        title='Perfiles',
        description='Define los perfiles disponibles y su presentación visual dentro del sistema.',
        source_name=source_name,
        projection_name=profiles_projection_name or projection_name,
        access_key=PROFILES_MANAGER_ACCESS_KEY,
    )

    def profiles_provider() -> ProfileCatalog:
        return read_manager_projection(
            stores.profiles,
            PROFILES_CONFIGURATION_SOURCE_KEY,
            ProfileCatalog,
            unavailable_causes=projection_unavailable_causes,
        ) or ProfileCatalog()

    users_administration = UsersAdministrationService(
        registry=stores.users_registry,
        promoted=stores.users_promoted,
        profiles=profiles_provider,
        directory=stores.users_directory,
    )
    users_manager = compose_users_manager(
        administration=users_administration,
        principal_provider=principal_provider,
        group_key='administration',
        access_key=USERS_MANAGER_ACCESS_KEY,
    )
    return ConfigurationManagerDependencies(
        navigation_source=navigation_source,
        navigation_projection=navigation_projection,
        navigation_projection_store=stores.navigation,
        tools_source=tools_source,
        tools_projection=tools_projection,
        access_source=access_source,
        access_projection=access_projection,
        profiles_projection=stores.profiles,
        principal_provider=principal_provider,
        profiles_module=profiles_manager.module,
        users_entry=users_manager.entry,
        kpi_registry_source=kpi_registry_source,
        kpi_registry_projection=kpi_registry_projection,
        kpi_registry_destinations=kpi_destinations,
        kpi_registry_projection_store=stores.kpi_registry,
        kpi_definitions_source=kpi_definitions_source,
        kpi_definitions_projection=kpi_definitions_projection,
        navigation_source_name=source_name,
        navigation_projection_name=projection_name,
        tools_source_name=source_name,
        tools_projection_name=projection_name,
        access_source_name=source_name,
        access_projection_name=projection_name,
        kpi_registry_source_name=source_name,
        kpi_registry_projection_name=kpi_projection_name or projection_name,
        kpi_definitions_source_name=source_name,
        kpi_definitions_projection_name=kpi_projection_name or projection_name,
    )


def read_manager_projection(
    store: ProjectionStore[PayloadT],
    source_key: SourceKey,
    payload_type: type[PayloadT],
    *,
    unavailable_causes: tuple[type[Exception], ...] = (),
) -> PayloadT | None:
    if not isinstance(unavailable_causes, tuple) or any(
        not isinstance(cause, type) or not issubclass(cause, Exception)
        for cause in unavailable_causes
    ):
        raise TypeError('Manager unavailable causes must be exception types')
    try:
        active = store.get_active(source_key)
    except (
        AdaAccessConfigurationProjectionError,
        ProfilesConfigurationProjectionError,
    ) as error:
        if isinstance(error.__cause__, unavailable_causes):
            raise ProjectionStoreError('Manager projection provider is unavailable') from error
        raise
    if active is None:
        return None
    if active.source_key != source_key:
        raise ValueError('Manager projection source key does not match request')
    if not isinstance(active.payload, payload_type):
        raise TypeError('Manager projection payload has an invalid type')
    return active.payload
