# Exporta provider y contrato de storage Cosmos para Definition.
from ada.web.kpis.definition.projection.cosmos.storage import (
    KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE,
    KPI_DEFINITION_PROJECTION_STORAGE_RESOURCES,
)
from ada.web.kpis.definition.projection.cosmos.store import (
    CosmosKpiDefinitionProjectionStore,
    CosmosKpiDefinitionProjectionStoreSettings,
)

__all__ = [
    'KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE',
    'KPI_DEFINITION_PROJECTION_STORAGE_RESOURCES',
    'CosmosKpiDefinitionProjectionStore',
    'CosmosKpiDefinitionProjectionStoreSettings',
]
