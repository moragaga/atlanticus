from ada.web.application.configuration_manager import (
    MANAGER_ROUTE_PREFIX,
    NAVIGATION_DRAFT_VALIDATION_SERVICE,
    NAVIGATION_PROJECTION_SERVICE,
    NAVIGATION_SOURCE_HISTORY_SERVICE,
    NAVIGATION_SOURCE_READER_SERVICE,
    NAVIGATION_SOURCE_SERVICE,
    TOOLS_DRAFT_VALIDATION_SERVICE,
    TOOLS_PROJECTION_SERVICE,
    TOOLS_SOURCE_HISTORY_SERVICE,
    TOOLS_SOURCE_READER_SERVICE,
    TOOLS_SOURCE_SERVICE,
    ConfigurationManagerDependencies,
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
    ToolManagerDraftValidationWorkflow,
    ToolManagerSourceWorkflow,
    build_configuration_manager_surface,
)
from ada.web.application.configuration_manager.composition import (
    NAVIGATION_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from atlanticus.web.manager import ManagerEntry, ManagerModule, ManagerPrincipal, ManagerSurface
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceSnapshot


class SourceStub:
    def __init__(self, source_key: str) -> None:
        self.source_key = SourceKey(source_key)

    def get_current(self) -> SourceSnapshot:
        return SourceSnapshot(self.source_key, None, None)


class ProjectionStub:
    pass


def profiles_module() -> ManagerModule:
    return ManagerModule(
        key='profiles',
        group_key='configuration',
        title='Profiles',
        route='/profiles',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey('profiles-configuration'),
        source_service='profiles.source',
        source_reader_service='profiles.source',
        source_history_service='profiles.source',
        projection_service='profiles.projection',
        draft_validation_service='profiles.validation',
        access_key='profiles.manage',
    )


def users_entry() -> ManagerEntry:
    return ManagerEntry(
        key='users',
        group_key='administration',
        title='Users',
        route='/users',
        order=10,
        layout=lambda _services: None,
        access_key=USERS_MANAGER_ACCESS_KEY,
        web_module=WebModule(name='atlanticus-users-administration'),
    )


def dependencies() -> ConfigurationManagerDependencies:
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        access_keys=(USERS_MANAGER_ACCESS_KEY, NAVIGATION_MANAGER_ACCESS_KEY, TOOLS_MANAGER_ACCESS_KEY),
        is_local=True,
    )
    return ConfigurationManagerDependencies(
        navigation_source=SourceStub('navigation'),
        navigation_projection=ProjectionStub(),
        tools_source=SourceStub('tools'),
        tools_projection=ProjectionStub(),
        principal_provider=lambda: principal,
        profiles_module=profiles_module(),
        users_entry=users_entry(),
    )


def test_surface_uses_generic_manager_contract_for_configuration_modules() -> None:
    definition = build_configuration_manager_surface(dependencies())
    surface = ManagerSurface(definition)

    assert definition.route_prefix == MANAGER_ROUTE_PREFIX == '/manager'
    assert tuple(entry.key for entry in surface.registry.entries) == ('users',)
    assert tuple(module.key for module in surface.registry.modules) == (
        'profiles',
        'navigation',
        'tools',
    )
    assert surface.registry.route_for(surface.registry.require_entry('users')) == '/manager/users'

    profiles, navigation, tools = definition.modules
    assert profiles.key == 'profiles'
    assert navigation.source_key == SourceKey('navigation')
    assert navigation.source_service == NAVIGATION_SOURCE_SERVICE
    assert navigation.source_reader_service == NAVIGATION_SOURCE_READER_SERVICE
    assert navigation.source_history_service == NAVIGATION_SOURCE_HISTORY_SERVICE
    assert navigation.projection_service == NAVIGATION_PROJECTION_SERVICE
    assert navigation.draft_validation_service == NAVIGATION_DRAFT_VALIDATION_SERVICE
    assert navigation.access_key == NAVIGATION_MANAGER_ACCESS_KEY

    assert tools.source_key == SourceKey('tools')
    assert tools.source_service == TOOLS_SOURCE_SERVICE
    assert tools.source_reader_service == TOOLS_SOURCE_READER_SERVICE
    assert tools.source_history_service == TOOLS_SOURCE_HISTORY_SERVICE
    assert tools.projection_service == TOOLS_PROJECTION_SERVICE
    assert tools.draft_validation_service == TOOLS_DRAFT_VALIDATION_SERVICE
    assert tools.access_key == TOOLS_MANAGER_ACCESS_KEY


def test_service_module_registers_configuration_capabilities() -> None:
    injected = dependencies()
    definition = build_configuration_manager_surface(injected)
    service_module = next(
        module
        for module in definition.web_modules
        if module.name == 'ada-configuration-manager-services'
    )
    services = ServiceRegistry()

    assert service_module.register_services is not None
    service_module.register_services(services)

    navigation_source = services.require(NAVIGATION_SOURCE_SERVICE)
    assert isinstance(navigation_source, NavigationManagerSourceWorkflow)
    assert services.require(NAVIGATION_SOURCE_READER_SERVICE) is navigation_source
    assert services.require(NAVIGATION_SOURCE_HISTORY_SERVICE) is navigation_source
    assert isinstance(
        services.require(NAVIGATION_DRAFT_VALIDATION_SERVICE),
        NavigationManagerDraftValidationWorkflow,
    )
    assert services.require(NAVIGATION_PROJECTION_SERVICE) is injected.navigation_projection

    tools_source = services.require(TOOLS_SOURCE_SERVICE)
    assert isinstance(tools_source, ToolManagerSourceWorkflow)
    assert services.require(TOOLS_SOURCE_READER_SERVICE) is tools_source
    assert services.require(TOOLS_SOURCE_HISTORY_SERVICE) is tools_source
    assert isinstance(
        services.require(TOOLS_DRAFT_VALIDATION_SERVICE),
        ToolManagerDraftValidationWorkflow,
    )
    assert services.require(TOOLS_PROJECTION_SERVICE) is injected.tools_projection
