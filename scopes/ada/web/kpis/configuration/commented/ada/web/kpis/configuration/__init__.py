# Este módulo expone únicamente el contrato público vigente de KPI Configuration.
# Las identidades Source y Projection provienen de los contratos genéricos de Atlanticus.

from ada.web.kpis.configuration.catalog import KpiCatalog
from ada.web.kpis.configuration.destinations import (
    KpiDestination,
    KpiDestinationCatalog,
    KpiDestinationCatalogProvider,
    KpiDestinationCatalogSnapshot,
    validate_kpi_configuration_destinations,
)
from ada.web.kpis.configuration.errors import (
    KpiConfigurationProjectionError,
    KpiConfigurationSourceError,
    KpiConfigurationValidationError,
)
from ada.web.kpis.configuration.models import (
    KpiConfiguration,
    KpiConfigurationBinding,
)
from ada.web.kpis.configuration.source_projection import (
    KpiProjectionBuilder,
    create_kpi_projection_service,
)
from ada.web.kpis.configuration.source_release import (
    KPI_SOURCE_DOCUMENT_TYPE,
    KPI_SOURCE_RESOURCE_PATH,
    KPI_SOURCE_SCHEMA_VERSION,
    KpiSourceCodec,
    KpiSourcePayload,
    KpiSourceRelease,
    KpiSourceService,
)

__version__ = '0.3.6'

__all__ = [
    'KPI_SOURCE_DOCUMENT_TYPE',
    'KPI_SOURCE_RESOURCE_PATH',
    'KPI_SOURCE_SCHEMA_VERSION',
    'KpiCatalog',
    'KpiConfiguration',
    'KpiConfigurationBinding',
    'KpiConfigurationProjectionError',
    'KpiConfigurationSourceError',
    'KpiConfigurationValidationError',
    'KpiDestination',
    'KpiDestinationCatalog',
    'KpiDestinationCatalogProvider',
    'KpiDestinationCatalogSnapshot',
    'KpiProjectionBuilder',
    'KpiSourceCodec',
    'KpiSourcePayload',
    'KpiSourceRelease',
    'KpiSourceService',
    'create_kpi_projection_service',
    'validate_kpi_configuration_destinations',
]
