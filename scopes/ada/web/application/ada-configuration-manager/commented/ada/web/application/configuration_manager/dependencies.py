# Declara las dependencias de dominio que la composition root recibe explícitamente.
from dataclasses import dataclass

from ada.configuration.tools_lifecycle import ToolLifecycleServices
from atlanticus.web.manager import ManagerPrincipalProvider
from atlanticus.web.navigation.configuration import NavigationConfigurationServices
from atlanticus.web.users.configuration import UsersConfigurationServices


@dataclass(frozen=True, slots=True)
class ConfigurationManagerDependencies:
    users: UsersConfigurationServices
    navigation: NavigationConfigurationServices
    tools: ToolLifecycleServices
    principal_provider: ManagerPrincipalProvider
    users_source_name: str = 'Source'
    users_projection_name: str = 'Projection'
    navigation_source_name: str = 'Source'
    navigation_projection_name: str = 'Projection'
    tools_source_name: str = 'Source'
    tools_projection_name: str = 'Projection'
    kpi_definitions_source_name: str = 'Source'
    kpi_definitions_projection_name: str = 'Projection'
    force_publish_enabled: bool = False
