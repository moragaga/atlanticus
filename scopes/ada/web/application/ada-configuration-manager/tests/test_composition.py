from types import SimpleNamespace

from ada.web.application.configuration_manager import (
    MANAGER_ROUTE_PREFIX,
    NAVIGATION_WORKFLOW_SERVICE,
    TOOLS_WORKFLOW_SERVICE,
    USERS_WORKFLOW_SERVICE,
    ConfigurationManagerDependencies,
    NavigationManagerWorkflowAdapter,
    ToolConfigurationManagerWorkflowAdapter,
    UsersManagerWorkflowAdapter,
    build_configuration_manager_surface,
)
from atlanticus.web.manager import ManagerPrincipal, ManagerSurface
from atlanticus.web.services import ServiceRegistry


class UsersAdministrationStub:
    def load_catalog(self):
        return None


def dependencies() -> ConfigurationManagerDependencies:
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        is_local=True,
    )

    def domain(administration=None):
        return SimpleNamespace(
            administration=administration or SimpleNamespace(),
            projection_workflow=SimpleNamespace(),
        )

    return ConfigurationManagerDependencies(
        users=domain(UsersAdministrationStub()),
        navigation=domain(),
        tools=domain(),
        principal_provider=lambda: principal,
    )


def test_surface_uses_manager_route_and_functional_module_order() -> None:
    definition = build_configuration_manager_surface(dependencies())
    surface = ManagerSurface(definition)

    assert definition.route_prefix == MANAGER_ROUTE_PREFIX == '/manager'
    assert definition.default_module_key == 'users'
    assert tuple(module.key for module in surface.registry.modules) == (
        'users',
        'navigation',
        'tools',
    )
    assert surface.default_path == '/manager/users'
    assert surface.registry.root_route == '/manager'


def test_surface_registers_explicit_access_contracts() -> None:
    definition = build_configuration_manager_surface(dependencies())
    users, navigation, tools = definition.modules

    assert users.access.view == 'users.manage'
    assert users.access.validate == 'users.manage'
    assert users.access.publish == 'users.manage'
    assert users.access.project == 'users.manage'
    assert navigation.access.view == 'navigation.manage'
    assert navigation.access.validate == 'navigation.manage'
    assert navigation.access.publish == 'navigation.manage'
    assert navigation.access.project == 'navigation.manage'
    assert tools.access.view == 'tools.manage'
    assert tools.access.validate == 'tools.manage'
    assert tools.access.publish == 'tools.manage'
    assert tools.access.project == 'tools.manage'


def test_tools_module_represents_the_application_tool_without_selector() -> None:
    definition = build_configuration_manager_surface(dependencies())
    tools = definition.modules[2]

    assert tools.key == 'tools'
    assert tools.title == 'Tool'
    assert tools.route == '/tools'
    assert tools.workflow_service == TOOLS_WORKFLOW_SERVICE
    assert tools.web_module is not None
    assert tools.web_module.name == 'ada-configuration-manager-tools'


def test_service_module_registers_only_surface_workflow_adapters() -> None:
    definition = build_configuration_manager_surface(dependencies())
    service_module = definition.web_modules[0]
    services = ServiceRegistry()

    assert service_module.register_services is not None
    service_module.register_services(services)

    assert isinstance(
        services.require(USERS_WORKFLOW_SERVICE),
        UsersManagerWorkflowAdapter,
    )
    assert isinstance(
        services.require(NAVIGATION_WORKFLOW_SERVICE),
        NavigationManagerWorkflowAdapter,
    )
    assert isinstance(
        services.require(TOOLS_WORKFLOW_SERVICE),
        ToolConfigurationManagerWorkflowAdapter,
    )
