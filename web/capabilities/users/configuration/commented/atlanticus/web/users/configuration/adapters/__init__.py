# Espejo comentado: misma lógica productiva con notas pedagógicas en español.
from atlanticus.web.users.configuration.adapters.file import (
    FileUsersConfigurationSettings,
    FileUsersConfigurationStore,
    FileUsersProjectionProfileCatalog,
    FileUsersProjectionRepository,
)
from atlanticus.web.users.configuration.adapters.memory import (
    MemoryDiscoveredUsersSource,
    MemoryUsersConfigurationStore,
    MemoryUsersProjectionRepository,
)
from atlanticus.web.users.configuration.adapters.sharepoint import (
    SharePointUsersConfigurationSettings,
    SharePointUsersConfigurationStore,
)

__all__ = [
    'FileUsersConfigurationSettings',
    'FileUsersConfigurationStore',
    'FileUsersProjectionProfileCatalog',
    'FileUsersProjectionRepository',
    'MemoryDiscoveredUsersSource',
    'MemoryUsersConfigurationStore',
    'MemoryUsersProjectionRepository',
    'SharePointUsersConfigurationSettings',
    'SharePointUsersConfigurationStore',
]
