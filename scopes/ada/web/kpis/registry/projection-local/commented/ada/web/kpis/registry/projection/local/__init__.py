# Expone el provider local del Registry.
# Este archivo es el espejo pedagógico del código productivo equivalente.

from ada.web.kpis.registry.projection.local.store import (
    LocalKpiRegistryProjectionStore,
    LocalKpiRegistryProjectionStoreSettings,
)

__all__ = [
    'LocalKpiRegistryProjectionStore',
    'LocalKpiRegistryProjectionStoreSettings',
]
