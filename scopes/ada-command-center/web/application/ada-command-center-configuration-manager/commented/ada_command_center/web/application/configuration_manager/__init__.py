# Espejo pedagógico: conserva exactamente el comportamiento del archivo productivo.
# Los comentarios documentan intención, ownership y flujo sin agregar compatibilidad ni lógica alternativa.
from ada_command_center.web.application.configuration_manager.administration import (
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
    CommandCenterAdministrationStores,
    compose_command_center_administration,
)
from ada_command_center.web.application.configuration_manager.application import (
    create_configuration_manager_application,
    create_configuration_manager_web_definition,
)
from ada_command_center.web.application.configuration_manager.composition import (
    ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,
    ALARM_CONFIGURATION_SOURCE_KEY,
    MANAGER_ROUTE_PREFIX,
    NAVIGATION_SOURCE_KEY,
    build_configuration_manager_surface,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    CommandCenterAdministrationDependencies,
    ConfigurationManagerDependencies,
)

__all__ = [
    'ALARM_CONFIGURATION_MANAGER_ACCESS_KEY',
    'ALARM_CONFIGURATION_SOURCE_KEY',
    'CommandCenterAdministrationDependencies',
    'CommandCenterAdministrationStores',
    'ConfigurationManagerDependencies',
    'MANAGER_ROUTE_PREFIX',
    'NAVIGATION_MANAGER_ACCESS_KEY',
    'NAVIGATION_SOURCE_KEY',
    'PROFILES_MANAGER_ACCESS_KEY',
    'USERS_MANAGER_ACCESS_KEY',
    'build_configuration_manager_surface',
    'compose_command_center_administration',
    'create_configuration_manager_application',
    'create_configuration_manager_web_definition',
]
