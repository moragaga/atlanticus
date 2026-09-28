from __future__ import annotations

from ada.web.access.configuration import create_ada_access_projection_service
from ada.web.application.configuration_manager.tool_kpi_registry_destinations import (
    ToolConfigurationKpiDestinationCatalogProvider,
)
from ada.web.application.configuration_manager.wiring import (
    ADA_ACCESS_SOURCE_KEY,
    KPI_DEFINITION_SOURCE_KEY,
    KPI_REGISTRY_SOURCE_KEY,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    ConfigurationManagerStores,
)
from ada.web.application.generic.master_projection.plan import (
    MasterProjectionPlanner,
    ProjectionDomain,
)
from ada.web.kpis.definition.configuration import create_kpi_definition_projection_service
from ada.web.kpis.registry.configuration import create_kpi_registry_projection_service
from ada.web.tools.configuration import create_tool_projection_service
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.navigation.configuration import create_navigation_projection_service
from atlanticus.web.profiles.configuration.source_projection import (
    create_profiles_projection_service,
)


# La composición reutiliza stores y constructores sin acoplarse a identidad o permisos Manager.
def compose_master_projection_planner(
    stores: ConfigurationManagerStores,
) -> MasterProjectionPlanner:
    if not isinstance(stores, ConfigurationManagerStores):
        raise TypeError('Master Projection requires configuration stores')
    destinations = ToolConfigurationKpiDestinationCatalogProvider(
        projection=stores.tools,
        source_key=TOOLS_SOURCE_KEY,
    )
    return MasterProjectionPlanner(
        domains=(
            ProjectionDomain(
                key=NAVIGATION_SOURCE_KEY,
                source=stores.navigation_source,
                projection=stores.navigation,
                service=create_navigation_projection_service(
                    source=stores.navigation_source,
                    projection=stores.navigation,
                ),
            ),
            ProjectionDomain(
                key=PROFILES_CONFIGURATION_SOURCE_KEY,
                source=stores.profiles_source,
                projection=stores.profiles,
                service=create_profiles_projection_service(
                    source=stores.profiles_source,
                    projection=stores.profiles,
                ),
            ),
            ProjectionDomain(
                key=TOOLS_SOURCE_KEY,
                source=stores.tools_source,
                projection=stores.tools,
                service=create_tool_projection_service(
                    source=stores.tools_source,
                    projection=stores.tools,
                ),
            ),
            ProjectionDomain(
                key=ADA_ACCESS_SOURCE_KEY,
                source=stores.access_source,
                projection=stores.access,
                service=create_ada_access_projection_service(
                    source=stores.access_source,
                    projection=stores.access,
                    profiles_projection=stores.profiles,
                    profiles_source_key=PROFILES_CONFIGURATION_SOURCE_KEY,
                ),
                # Access depende del target Profiles efectivo y exacto.
                requires=(PROFILES_CONFIGURATION_SOURCE_KEY,),
            ),
            ProjectionDomain(
                key=KPI_REGISTRY_SOURCE_KEY,
                source=stores.kpi_registry_source,
                projection=stores.kpi_registry,
                service=create_kpi_registry_projection_service(
                    source=stores.kpi_registry_source,
                    projection=stores.kpi_registry,
                    destinations=destinations,
                ),
                # Registry depende del Tool efectivamente proyectado.
                requires=(TOOLS_SOURCE_KEY,),
            ),
            ProjectionDomain(
                key=KPI_DEFINITION_SOURCE_KEY,
                source=stores.kpi_definitions_source,
                projection=stores.kpi_definitions,
                service=create_kpi_definition_projection_service(
                    source=stores.kpi_definitions_source,
                    projection=stores.kpi_definitions,
                    kpi_registry_projection=stores.kpi_registry,
                    kpi_registry_source_key=KPI_REGISTRY_SOURCE_KEY,
                ),
                # Definition depende del Registry efectivamente proyectado.
                requires=(KPI_REGISTRY_SOURCE_KEY,),
            ),
        ),
        profiles_key=PROFILES_CONFIGURATION_SOURCE_KEY,
        # El lector de catálogo no invoca el recovery provider basado en promovidos.
        users_snapshot_ids=stores.users_snapshot_ids,
    )
