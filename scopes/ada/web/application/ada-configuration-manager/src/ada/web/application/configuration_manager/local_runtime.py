from __future__ import annotations

import os
from pathlib import Path
from typing import Generic, TypeVar

from ada.web.application.configuration_manager.application import (
    create_configuration_manager_application,
)
from ada.web.application.configuration_manager.composition import (
    KPI_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada.web.application.configuration_manager.tool_kpi_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiSourceService,
    create_kpi_projection_service,
)
from ada.web.kpis.definition import (
    KpiDefinitionCatalog,
    KpiDefinitionSourceService,
    create_kpi_definition_projection_service,
)
from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolSourceService,
    create_tool_projection_service,
)
from atlanticus.web.compositions.profiles_manager import compose_profiles_manager
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
    create_navigation_projection_service,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey

PayloadT = TypeVar('PayloadT')

NAVIGATION_SOURCE_KEY = SourceKey('navigation')
TOOLS_SOURCE_KEY = SourceKey('tools')
KPI_SOURCE_KEY = SourceKey('kpis')
KPI_DEFINITION_SOURCE_KEY = SourceKey('kpi-definitions')


class InProcessProjectionStore(ProjectionStore[PayloadT], Generic[PayloadT]):
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[PayloadT]] = {}

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        return self._active.get(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[PayloadT],
    ) -> ProjectionRecord[PayloadT]:
        self._active[projection.source_key] = projection
        return projection


def create_local_configuration_manager_dependencies(
    *,
    source_root: Path | None = None,
) -> ConfigurationManagerDependencies:
    root = source_root or _source_root()
    source_store = LocalSourceStore(LocalSourceSettings(root=root))

    navigation_projection_store = InProcessProjectionStore[NavigationConfigurationCatalog]()
    tools_projection_store = InProcessProjectionStore[ToolConfiguration]()
    kpi_projection_store = InProcessProjectionStore[KpiConfiguration]()
    kpi_definition_projection_store = InProcessProjectionStore[KpiDefinitionCatalog]()
    profiles_projection_store = InProcessProjectionStore()

    navigation_source = NavigationSourceService(
        source=source_store,
        source_key=NAVIGATION_SOURCE_KEY,
    )
    tools_source = ToolSourceService(source=source_store, source_key=TOOLS_SOURCE_KEY)
    kpis_source = KpiSourceService(source=source_store, source_key=KPI_SOURCE_KEY)
    kpi_definitions_source = KpiDefinitionSourceService(
        source=source_store,
        source_key=KPI_DEFINITION_SOURCE_KEY,
    )

    navigation_projection = create_navigation_projection_service(
        source=source_store,
        projection=navigation_projection_store,
    )
    tools_projection = create_tool_projection_service(
        source=source_store,
        projection=tools_projection_store,
    )
    kpi_destinations = ToolConfigurationKpiDestinationCatalogProvider(
        projection=tools_projection_store,
        source_key=TOOLS_SOURCE_KEY,
    )
    kpis_projection = create_kpi_projection_service(
        source=source_store,
        projection=kpi_projection_store,
        destinations=kpi_destinations,
    )
    kpi_definitions_projection = create_kpi_definition_projection_service(
        source=source_store,
        projection=kpi_definition_projection_store,
        kpi_configuration_projection=kpi_projection_store,
        kpi_configuration_source_key=KPI_SOURCE_KEY,
    )

    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        access_keys=(
            PROFILES_MANAGER_ACCESS_KEY,
            NAVIGATION_MANAGER_ACCESS_KEY,
            TOOLS_MANAGER_ACCESS_KEY,
            KPI_MANAGER_ACCESS_KEY,
        ),
        is_local=True,
    )
    profiles_manager = compose_profiles_manager(
        source_store=source_store,
        projection_store=profiles_projection_store,
        principal_provider=lambda: principal,
        group_key='configuration',
        access_key=PROFILES_MANAGER_ACCESS_KEY,
    )
    return ConfigurationManagerDependencies(
        navigation_source=navigation_source,
        navigation_projection=navigation_projection,
        tools_source=tools_source,
        tools_projection=tools_projection,
        principal_provider=lambda: principal,
        profiles_module=profiles_manager.module,
        kpis_source=kpis_source,
        kpis_projection=kpis_projection,
        kpi_destinations=kpi_destinations,
        kpi_configuration_projection=kpi_projection_store,
        kpi_definitions_source=kpi_definitions_source,
        kpi_definitions_projection=kpi_definitions_projection,
        navigation_source_name='Local Source',
        navigation_projection_name='In-process Projection',
        tools_source_name='Local Source',
        tools_projection_name='In-process Projection',
        kpis_source_name='Local Source',
        kpis_projection_name='In-process Projection',
        kpi_definitions_source_name='Local Source',
        kpi_definitions_projection_name='In-process Projection',
    )


def create_local_configuration_manager_application(
    *,
    source_root: Path | None = None,
) -> WebApplicationRuntime:
    return create_configuration_manager_application(
        create_local_configuration_manager_dependencies(source_root=source_root)
    )


def _source_root() -> Path:
    configured = os.getenv('ADA_CONFIGURATION_MANAGER_SOURCE_ROOT')
    if configured is not None and configured.strip():
        return Path(configured).expanduser().resolve()
    return Path.cwd() / '.runtime' / 'configuration-manager' / 'source'
