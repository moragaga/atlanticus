# Construye servicios y stores concretos y entrega dependencias consistentes a la composición del Manager.
# Este espejo conserva exactamente el mismo AST y comportamiento que producción.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from ada.web.access.configuration import (
    ADA_ACCESS_SOURCE_KEY,
    AdaAccessConfiguration,
    AdaAccessSourceService,
    create_ada_access_projection_service,
)
from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.application.configuration_manager.composition import (
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.dependencies import ConfigurationManagerDependencies
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    compose_operational_catalog_manager_contracts,
)
from ada.web.application.configuration_manager.tool_kpi_registry_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.kpis.definition.configuration import (
    KPI_DEFINITION_SOURCE_KEY,
    KpiDefinitionSourceService,
    create_kpi_definition_projection_service,
)
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.registry.configuration import (
    KPI_REGISTRY_SOURCE_KEY,
    KpiRegistrySourceService,
    create_kpi_registry_projection_service,
)
from ada.web.kpis.registry.models import KpiRegistry
from ada.web.operational.identification import OperationalIdentificationService
from ada.web.operational.identification.models import OperationalDocument
from ada.web.tools.configuration import (
    TOOLS_SOURCE_KEY,
    ToolConfiguration,
    ToolSourceService,
    create_tool_projection_service,
)
from atlanticus.web.compositions.navigation_manager import compose_navigation_manager
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    compose_profiles_manager,
)
from atlanticus.web.compositions.users_manager import (
    compose_users_manager,
    compose_users_projection_manager,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.configuration import (
    NAVIGATION_SOURCE_KEY,
    NavigationConfigurationCatalog,
    NavigationProfileOption,
)
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.errors import ProjectionStoreError
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.recovery import ApprovedUsersSnapshot, UsersApprovedRecoveryService
from atlanticus.web.users.store import (
    UsersAdministrationStore,
    UsersDirectoryReader,
    UsersRegistryStore,
)


PayloadT = TypeVar('PayloadT')


@dataclass(frozen=True, slots=True)
# Clase con responsabilidad y estado explícitos dentro de esta frontera.
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
    operational_source: SourceStore | None = None
    operational: ProjectionStore[OperationalDocument] | None = None
    users_recovery: (
        UsersApprovedRecoveryService | Callable[[], UsersApprovedRecoveryService] | None
    ) = None
    users_snapshot_ids: Callable[[], tuple[str, ...]] | None = None
    users_snapshot_summaries: Callable[[], tuple[tuple[str, str | None], ...]] | None = None
    users_read_snapshot: Callable[[str], ApprovedUsersSnapshot] | None = None

    # Expone o ejecuta la responsabilidad `__post_init__` sin cambiar contratos externos.
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
                raise TypeError(f'Configuration Manager {name} must implement {expected.__name__}')
        if (self.operational_source is None) != (self.operational is None):
            raise ValueError('Operational source and projection must be injected together')
        if self.operational_source is not None and not isinstance(
            self.operational_source, SourceStore
        ):
            raise TypeError('Operational source must implement SourceStore')
        if self.operational is not None and not isinstance(self.operational, ProjectionStore):
            raise TypeError('Operational projection must implement ProjectionStore')
        if self.users_directory is not None and not isinstance(
            self.users_directory, UsersDirectoryReader
        ):
            raise TypeError('Configuration Manager directory must implement UsersDirectoryReader')
        if (self.users_recovery is None) != (self.users_snapshot_ids is None):
            raise ValueError('Users recovery and snapshot catalog must be injected together')
        if (
            self.users_recovery is not None
            and not isinstance(self.users_recovery, UsersApprovedRecoveryService)
            and not callable(self.users_recovery)
        ):
            raise TypeError('Users recovery service has an invalid type')
        if self.users_snapshot_ids is not None and not callable(self.users_snapshot_ids):
            raise TypeError('Users snapshot catalog must be callable')
        if any(
            provider is not None
            for provider in (
                self.users_snapshot_summaries,
                self.users_read_snapshot,
            )
        ) and (
            self.users_recovery is None
            or self.users_snapshot_ids is None
            or not callable(self.users_snapshot_summaries)
            or not callable(self.users_read_snapshot)
        ):
            raise ValueError('Users snapshot metadata providers must be injected together')


# Expone o ejecuta la responsabilidad `compose_configuration_manager_dependencies` sin cambiar contratos externos.
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

    operational_service = (
        OperationalIdentificationService(
            source_store=stores.operational_source,
            projections=stores.operational,
            users=stores.users_promoted,
        )
        if stores.operational_source is not None and stores.operational is not None
        else None
    )
    operational_catalog_contracts = (
        compose_operational_catalog_manager_contracts(
            service=operational_service,
            source_store=stores.operational_source,
            projection_store=stores.operational,
            audit_actor_provider=lambda: principal_provider().subject_id,
        )
        if operational_service is not None
        and stores.operational_source is not None
        and stores.operational is not None
        else None
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

    # Expone o ejecuta la responsabilidad `profiles_provider` sin cambiar contratos externos.
    def profiles_provider() -> ProfileCatalog:
        return (
            read_manager_projection(
                stores.profiles,
                PROFILES_CONFIGURATION_SOURCE_KEY,
                ProfileCatalog,
                unavailable_causes=projection_unavailable_causes,
            )
            or ProfileCatalog()
        )

    # Convierte Profiles al contrato neutral de Navigation sin crear dependencia inversa.
    def navigation_profile_options() -> tuple[NavigationProfileOption, ...]:
        catalog = profiles_provider()
        return tuple(
            NavigationProfileOption(profile.key, profile.label)
            for profile in catalog.all()
            if profile.key not in {'root', 'local'}
        )

    navigation_manager = compose_navigation_manager(
        source_store=stores.navigation_source,
        projection_store=stores.navigation,
        principal_provider=principal_provider,
        group_key='configuration',
        title='Navegación',
        description='Rutas, secciones y perfiles habilitados en la navegación de ADA.',
        source_key=NAVIGATION_SOURCE_KEY,
        source_name=source_name,
        projection_name=projection_name,
        access_key=NAVIGATION_MANAGER_ACCESS_KEY,
        profile_options_provider=navigation_profile_options,
    )

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
        title='Usuarios',
        access_key=USERS_MANAGER_ACCESS_KEY,
    )
    users_projection_entry = (
        compose_users_projection_manager(
            recovery=stores.users_recovery,
            snapshot_ids=stores.users_snapshot_ids,
            snapshot_summaries=stores.users_snapshot_summaries,
            read_snapshot=stores.users_read_snapshot,
            principal_provider=principal_provider,
            group_key='administration',
            access_key=USERS_MANAGER_ACCESS_KEY,
        )
        if stores.users_recovery is not None and stores.users_snapshot_ids is not None
        else None
    )
    return ConfigurationManagerDependencies(
        users_projection_entry=users_projection_entry,
        navigation_module=navigation_manager.module,
        navigation_projection_store=stores.navigation,
        tools_source=tools_source,
        tools_projection=tools_projection,
        access_source=access_source,
        access_projection=access_projection,
        profiles_projection=stores.profiles,
        principal_provider=principal_provider,
        profiles_module=profiles_manager.module,
        users_entry=users_manager.entry,
        operational_service=operational_service,
        operational_catalog_contracts=operational_catalog_contracts,
        operational_users=stores.users_promoted.list_users
        if operational_service is not None
        else None,
        kpi_registry_source=kpi_registry_source,
        kpi_registry_projection=kpi_registry_projection,
        kpi_registry_destinations=kpi_destinations,
        kpi_registry_projection_store=stores.kpi_registry,
        kpi_definitions_source=kpi_definitions_source,
        kpi_definitions_projection=kpi_definitions_projection,
        tools_source_name=source_name,
        tools_projection_name=projection_name,
        operational_source_name=source_name,
        operational_projection_name=projection_name,
        access_source_name=source_name,
        access_projection_name=projection_name,
        kpi_registry_source_name=source_name,
        kpi_registry_projection_name=kpi_projection_name or projection_name,
        kpi_definitions_source_name=source_name,
        kpi_definitions_projection_name=kpi_projection_name or projection_name,
    )


# Expone o ejecuta la responsabilidad `read_manager_projection` sin cambiar contratos externos.
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
