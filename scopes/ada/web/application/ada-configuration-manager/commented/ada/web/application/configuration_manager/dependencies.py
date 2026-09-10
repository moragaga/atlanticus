# Declara las dependencias de dominio que la composition root recibe explícitamente.
from dataclasses import dataclass

from ada.web.kpis.configuration import (
    KpiConfigurationServices,
    KpiDestinationCatalogProvider,
)
from ada.web.kpis.definition import (
    KpiDefinitionAuthorityProvider,
    KpiDefinitionServices,
)
from ada.web.tools.configuration import ToolLifecycleServices
from atlanticus.web.manager import ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import NavigationConfigurationServices
from atlanticus.web.users.configuration import UsersConfigurationServices


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    users: UsersConfigurationServices
    navigation: NavigationConfigurationServices
    tools: ToolLifecycleServices
    principal_provider: ManagerPrincipalProvider
    kpis: KpiConfigurationServices | None = None
    kpi_destinations: KpiDestinationCatalogProvider | None = None
    kpi_definitions: KpiDefinitionServices | None = None
    kpi_definition_authority: KpiDefinitionAuthorityProvider | None = None
    users_source_name: str = 'Source'
    users_projection_name: str = 'Projection'
    navigation_source_name: str = 'Source'
    navigation_projection_name: str = 'Projection'
    tools_source_name: str = 'Source'
    tools_projection_name: str = 'Projection'
    kpis_source_name: str = 'Source'
    kpis_projection_name: str = 'Projection'
    kpi_definitions_source_name: str = 'Source'
    kpi_definitions_projection_name: str = 'Projection'
    force_publish_enabled: bool = False

    def __post_init__(self) -> None:
        if (self.kpis is None) != (self.kpi_destinations is None):
            raise ValueError(
                'KPI services and KPI destination catalog provider must be injected together'
            )
        if (self.kpi_definitions is None) != (self.kpi_definition_authority is None):
            raise ValueError(
                'KPI Definition services and authority provider must be injected together'
            )
        if self.kpi_definitions is not None and self.kpis is None:
            raise ValueError('KPI Definition requires KPI Configuration')
