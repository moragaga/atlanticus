# API pública del provider Cosmos y su contrato declarativo de storage.
from atlanticus.web.profiles.projection.cosmos.storage import (
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    PROFILES_PROJECTION_STORAGE_RESOURCES,
)
from atlanticus.web.profiles.projection.cosmos.store import (
    CosmosProfilesProjectionStore,
    CosmosProfilesProjectionStoreSettings,
)

__all__ = [
    'PROFILES_PROJECTION_STORAGE_RESOURCE',
    'PROFILES_PROJECTION_STORAGE_RESOURCES',
    'CosmosProfilesProjectionStore',
    'CosmosProfilesProjectionStoreSettings',
]
