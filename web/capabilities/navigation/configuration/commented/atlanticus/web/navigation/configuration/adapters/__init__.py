# Espejo pedagógico: exports de adapters intercambiables.
from atlanticus.web.navigation.configuration.adapters.cosmos import (
    CosmosNavigationProjectionRepository,
    CosmosNavigationProjectionSettings,
)
from atlanticus.web.navigation.configuration.adapters.file import (
    FileNavigationConfigurationSettings,
    FileNavigationConfigurationStore,
    FileNavigationProjectionRepository,
    FileNavigationProjectionSettings,
)
from atlanticus.web.navigation.configuration.adapters.memory import (
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.adapters.sharepoint import (
    SharePointNavigationConfigurationSettings,
    SharePointNavigationConfigurationStore,
)

__all__ = [
    'CosmosNavigationProjectionRepository',
    'CosmosNavigationProjectionSettings',
    'FileNavigationConfigurationSettings',
    'FileNavigationConfigurationStore',
    'FileNavigationProjectionRepository',
    'FileNavigationProjectionSettings',
    'MemoryNavigationConfigurationStore',
    'MemoryNavigationProjectionRepository',
    'SharePointNavigationConfigurationSettings',
    'SharePointNavigationConfigurationStore',
]
