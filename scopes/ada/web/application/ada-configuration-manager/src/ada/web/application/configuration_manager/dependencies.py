from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada.web.access.configuration import AdaAccessConfiguration, AdaAccessSourceService
from ada.web.application.configuration_manager.operational_catalog_workflows import (
    OperationalCatalogManagerContracts,
)
from ada.web.kpis.definition.configuration import KpiDefinitionSourceService
from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.registry.configuration import KpiDestinationCatalogProvider, KpiRegistrySourceService
from ada.web.kpis.registry.models import KpiRegistry
from ada.web.operational.identification import OperationalIdentificationService
from ada.web.tools.configuration import ToolConfiguration, ToolSourceService
from atlanticus.web.manager import ManagerEntry, ManagerModule, ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.users.models import ManagedUser


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    navigation_module: ManagerModule
    navigation_projection_store: ProjectionStore[NavigationConfigurationCatalog]
    tools_source: ToolSourceService
    tools_projection: SourceProjectionService[ToolConfiguration]
    access_source: AdaAccessSourceService
    access_projection: SourceProjectionService[AdaAccessConfiguration]
    profiles_projection: ProjectionStore[ProfileCatalog]
    principal_provider: ManagerPrincipalProvider
    profiles_module: ManagerModule
    users_entry: ManagerEntry
    users_projection_entry: ManagerEntry | None = None
    operational_service: OperationalIdentificationService | None = None
    operational_users: Callable[[], tuple[ManagedUser, ...]] | None = None
    operational_catalog_contracts: OperationalCatalogManagerContracts | None = None
    kpi_registry_source: KpiRegistrySourceService | None = None
    kpi_registry_projection: SourceProjectionService[KpiRegistry] | None = None
    kpi_registry_destinations: KpiDestinationCatalogProvider | None = None
    kpi_registry_projection_store: ProjectionStore[KpiRegistry] | None = None
    kpi_definitions_source: KpiDefinitionSourceService | None = None
    kpi_definitions_projection: SourceProjectionService[KpiDefinitionCatalog] | None = None
    tools_source_name: str = 'Source'
    tools_projection_name: str = 'Projection'
    operational_source_name: str = 'Source'
    operational_projection_name: str = 'Projection'
    access_source_name: str = 'Source'
    access_projection_name: str = 'Projection'
    kpi_registry_source_name: str = 'Source'
    kpi_registry_projection_name: str = 'Projection'
    kpi_definitions_source_name: str = 'Source'
    kpi_definitions_projection_name: str = 'Projection'

    def __post_init__(self) -> None:
        if (self.operational_service is None) != (self.operational_users is None):
            raise ValueError('Operational service and managed users must be injected together')
        if self.operational_catalog_contracts is not None and self.operational_service is None:
            raise ValueError('Operational catalog contracts require operational service')
        if self.operational_service is not None and self.operational_catalog_contracts is None:
            raise ValueError('Operational service requires operational catalog contracts')
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
        if self.kpi_definitions_source is not None and self.kpi_registry_projection_store is None:
            raise ValueError('KPI Definition requires the KPI Registry projection store')
