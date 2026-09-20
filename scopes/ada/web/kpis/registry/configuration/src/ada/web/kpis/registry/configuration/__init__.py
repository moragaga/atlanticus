from ada.web.kpis.registry.catalog import KpiCatalog
from ada.web.kpis.registry.errors import KpiRegistryValidationError
from ada.web.kpis.registry.models import KpiRegistry, KpiRegistryBinding
from ada.web.kpis.registry.configuration.destinations import (
    KpiDestination,
    KpiDestinationCatalog,
    KpiDestinationCatalogProvider,
    KpiDestinationCatalogSnapshot,
    validate_kpi_registry_destinations,
)
from ada.web.kpis.registry.configuration.errors import (
    KpiRegistryProjectionError,
    KpiRegistrySourceError,
)
from ada.web.kpis.registry.configuration.projection_record import (
    KPI_REGISTRY_PROJECTION_DOCUMENT_TYPE,
    KPI_REGISTRY_PROJECTION_SCHEMA_VERSION,
    kpi_registry_projection_from_document,
    kpi_registry_projection_to_document,
)
from ada.web.kpis.registry.configuration.source_projection import (
    KpiRegistryProjectionBuilder,
    create_kpi_registry_projection_service,
)
from ada.web.kpis.registry.configuration.source_release import (
    KPI_REGISTRY_SOURCE_DOCUMENT_TYPE,
    KPI_REGISTRY_SOURCE_RESOURCE_PATH,
    KPI_REGISTRY_SOURCE_SCHEMA_VERSION,
    KpiRegistrySourceCodec,
    KpiRegistrySourcePayload,
    KpiRegistrySourceRelease,
    KpiRegistrySourceService,
)

__version__ = '0.1.0'

__all__ = [
    'KPI_REGISTRY_PROJECTION_DOCUMENT_TYPE',
    'KPI_REGISTRY_PROJECTION_SCHEMA_VERSION',
    'KPI_REGISTRY_SOURCE_DOCUMENT_TYPE',
    'KPI_REGISTRY_SOURCE_RESOURCE_PATH',
    'KPI_REGISTRY_SOURCE_SCHEMA_VERSION',
    'KpiCatalog',
    'KpiDestination',
    'KpiDestinationCatalog',
    'KpiDestinationCatalogProvider',
    'KpiDestinationCatalogSnapshot',
    'KpiRegistry',
    'KpiRegistryBinding',
    'KpiRegistryProjectionBuilder',
    'KpiRegistryProjectionError',
    'KpiRegistrySourceCodec',
    'KpiRegistrySourceError',
    'KpiRegistrySourcePayload',
    'KpiRegistrySourceRelease',
    'KpiRegistrySourceService',
    'KpiRegistryValidationError',
    'create_kpi_registry_projection_service',
    'kpi_registry_projection_from_document',
    'kpi_registry_projection_to_document',
    'validate_kpi_registry_destinations',
]
