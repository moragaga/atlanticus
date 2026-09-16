# Espejo pedagógico del contrato productivo.
# La implementación conserva las mismas clases y funciones; estos comentarios explican la intención general.
# Definition consume directamente la proyección tipada de KPI Configuration y delega identidad/versionado a Atlanticus.
from ada.web.kpis.definition.coverage import (
    KpiDefinitionCatalog,
    KpiDefinitionCoverageItem,
    KpiDefinitionCoverageStatus,
    build_kpi_definition_coverage,
    validate_kpi_definition_configuration,
)
from ada.web.kpis.definition.errors import (
    KpiDefinitionProjectionError,
    KpiDefinitionSourceError,
    KpiDefinitionValidationError,
)
from ada.web.kpis.definition.models import (
    KpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionFields,
)
from ada.web.kpis.definition.source_projection import (
    KpiDefinitionProjectionBuilder,
    create_kpi_definition_projection_service,
)
from ada.web.kpis.definition.source_release import (
    KPI_DEFINITION_SOURCE_DOCUMENT_TYPE,
    KPI_DEFINITION_SOURCE_RESOURCE_PATH,
    KPI_DEFINITION_SOURCE_SCHEMA_VERSION,
    KpiDefinitionSourceCodec,
    KpiDefinitionSourcePayload,
    KpiDefinitionSourceRelease,
    KpiDefinitionSourceService,
)

__version__ = '0.6.0'

__all__ = [
    'KPI_DEFINITION_SOURCE_DOCUMENT_TYPE',
    'KPI_DEFINITION_SOURCE_RESOURCE_PATH',
    'KPI_DEFINITION_SOURCE_SCHEMA_VERSION',
    'KpiDefinition',
    'KpiDefinitionCatalog',
    'KpiDefinitionConfiguration',
    'KpiDefinitionCoverageItem',
    'KpiDefinitionCoverageStatus',
    'KpiDefinitionFields',
    'KpiDefinitionProjectionBuilder',
    'KpiDefinitionProjectionError',
    'KpiDefinitionSourceCodec',
    'KpiDefinitionSourceError',
    'KpiDefinitionSourcePayload',
    'KpiDefinitionSourceRelease',
    'KpiDefinitionSourceService',
    'KpiDefinitionValidationError',
    'build_kpi_definition_coverage',
    'create_kpi_definition_projection_service',
    'validate_kpi_definition_configuration',
]
