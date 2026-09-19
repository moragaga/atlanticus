# API pública del provider Cosmos y de su topología standalone por defecto.
from ada.web.access.projection.cosmos.storage import (
    ADA_ACCESS_PROJECTION_STORAGE_RESOURCE,
    ADA_ACCESS_PROJECTION_STORAGE_RESOURCES,
)
from ada.web.access.projection.cosmos.store import (
    CosmosAdaAccessProjectionStore,
    CosmosAdaAccessProjectionStoreSettings,
)

__all__ = [
    'ADA_ACCESS_PROJECTION_STORAGE_RESOURCE',
    'ADA_ACCESS_PROJECTION_STORAGE_RESOURCES',
    'CosmosAdaAccessProjectionStore',
    'CosmosAdaAccessProjectionStoreSettings',
]
