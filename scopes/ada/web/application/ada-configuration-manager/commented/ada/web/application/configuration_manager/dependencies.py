# Espejo pedagógico: ADA compone la capability Users ya construida y no adopta ownership de su lifecycle.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiDestinationCatalogProvider,
    KpiSourceService,
)
from ada.web.kpis.definition import KpiDefinitionCatalog, KpiDefinitionSourceService
from ada.web.tools.configuration import ToolConfiguration, ToolSourceService
from atlanticus.web.manager import ManagerEntry, ManagerModule, ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
)
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    navigation_source: NavigationSourceService
    navigation_projection: SourceProjectionService[NavigationConfigurationCatalog]
    tools_source: ToolSourceService
    tools_projection: SourceProjectionService[ToolConfiguration]
    principal_provider: ManagerPrincipalProvider
    profiles_module: ManagerModule
    users_entry: ManagerEntry
    kpis_source: KpiSourceService | None = None
    kpis_projection: SourceProjectionService[KpiConfiguration] | None = None
    kpi_destinations: KpiDestinationCatalogProvider | None = None
    kpi_configuration_projection: ProjectionStore[KpiConfiguration] | None = None
    kpi_definitions_source: KpiDefinitionSourceService | None = None
    kpi_definitions_projection: SourceProjectionService[KpiDefinitionCatalog] | None = None
    navigation_source_name: str = 'Source'
    navigation_projection_name: str = 'Projection'
    tools_source_name: str = 'Source'
    tools_projection_name: str = 'Projection'
    kpis_source_name: str = 'Source'
    kpis_projection_name: str = 'Projection'
    kpi_definitions_source_name: str = 'Source'
    kpi_definitions_projection_name: str = 'Projection'

    def __post_init__(self) -> None:
        kpi_contract = (
            self.kpis_source,
            self.kpis_projection,
            self.kpi_destinations,
        )
        if any(value is not None for value in kpi_contract) and not all(
            value is not None for value in kpi_contract
        ):
            raise ValueError(
                'KPI source, projection and destination provider must be injected together'
            )
        definition_contract = (
            self.kpi_definitions_source,
            self.kpi_definitions_projection,
        )
        if any(value is not None for value in definition_contract) and not all(
            value is not None for value in definition_contract
        ):
            raise ValueError('KPI Definition source and projection must be injected together')
        if self.kpi_definitions_source is not None and self.kpis_source is None:
            raise ValueError('KPI Definition requires KPI Configuration')
        if (
            self.kpi_definitions_source is not None
            and self.kpi_configuration_projection is None
        ):
            raise ValueError(
                'KPI Definition requires the KPI Configuration projection store'
            )
