# Dependencias explícitas de la aplicación administrativa.
# ADA Access recibe Source, Projection y la Projection de Profiles requerida para validar assignments.

from __future__ import annotations

from dataclasses import dataclass

from ada.web.access.configuration import AdaAccessConfiguration, AdaAccessSourceService
from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.registry.configuration import (
    KpiDestinationCatalogProvider,
    KpiRegistrySourceService,
)
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.configuration import KpiDefinitionSourceService
from ada.web.tools.configuration import ToolConfiguration, ToolSourceService
from atlanticus.web.manager import ManagerEntry, ManagerModule, ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    navigation_source: NavigationSourceService
    navigation_projection: SourceProjectionService[NavigationConfigurationCatalog]
    tools_source: ToolSourceService
    tools_projection: SourceProjectionService[ToolConfiguration]
    access_source: AdaAccessSourceService
    access_projection: SourceProjectionService[AdaAccessConfiguration]
    profiles_projection: ProjectionStore[ProfileCatalog]
    principal_provider: ManagerPrincipalProvider
    profiles_module: ManagerModule
    users_entry: ManagerEntry
    kpi_registry_source: KpiRegistrySourceService | None = None
    kpi_registry_projection: SourceProjectionService[KpiRegistry] | None = None
    kpi_registry_destinations: KpiDestinationCatalogProvider | None = None
    kpi_registry_projection_store: ProjectionStore[KpiRegistry] | None = None
    kpi_definitions_source: KpiDefinitionSourceService | None = None
    kpi_definitions_projection: SourceProjectionService[KpiDefinitionCatalog] | None = None
    navigation_source_name: str = 'Source'
    navigation_projection_name: str = 'Projection'
    tools_source_name: str = 'Source'
    tools_projection_name: str = 'Projection'
    access_source_name: str = 'Source'
    access_projection_name: str = 'Projection'
    kpi_registry_source_name: str = 'Source'
    kpi_registry_projection_name: str = 'Projection'
    kpi_definitions_source_name: str = 'Source'
    kpi_definitions_projection_name: str = 'Projection'

    def __post_init__(self) -> None:
        kpi_contract = (
            self.kpi_registry_source,
            self.kpi_registry_projection,
            self.kpi_registry_destinations,
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
        if self.kpi_definitions_source is not None and self.kpi_registry_source is None:
            raise ValueError('KPI Definition requires KPI Registry')
        if (
            self.kpi_definitions_source is not None
            and self.kpi_registry_projection_store is None
        ):
            raise ValueError(
                'KPI Definition requires the KPI Registry projection store'
            )
