# Expone la API pública de la composition root administrativa de ADA.
from ada.web.application.configuration_manager.application import (
    create_configuration_manager_application,
    create_configuration_manager_web_definition,
)
from ada.web.application.configuration_manager.composition import (
    MANAGER_ROUTE_PREFIX,
    NAVIGATION_WORKFLOW_SERVICE,
    TOOLS_WORKFLOW_SERVICE,
    USERS_WORKFLOW_SERVICE,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada.web.application.configuration_manager.workflows import (
    NavigationManagerWorkflowAdapter,
    ToolConfigurationManagerWorkflowAdapter,
    UsersManagerWorkflowAdapter,
)

__all__ = [
    'ConfigurationManagerDependencies',
    'MANAGER_ROUTE_PREFIX',
    'NAVIGATION_WORKFLOW_SERVICE',
    'NavigationManagerWorkflowAdapter',
    'TOOLS_WORKFLOW_SERVICE',
    'ToolConfigurationManagerWorkflowAdapter',
    'USERS_WORKFLOW_SERVICE',
    'UsersManagerWorkflowAdapter',
    'build_configuration_manager_surface',
    'create_configuration_manager_application',
    'create_configuration_manager_web_definition',
]
