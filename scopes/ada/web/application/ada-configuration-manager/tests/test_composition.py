from types import SimpleNamespace

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
    USERS_DRAFT_VALIDATION_SERVICE,
    USERS_PROJECTION_SERVICE,
    USERS_SOURCE_HISTORY_SERVICE,
    USERS_SOURCE_READER_SERVICE,
    USERS_SOURCE_SERVICE,
    ConfigurationManagerDependencies,
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
    ToolManagerDraftValidationWorkflow,
    ToolManagerSourceWorkflow,
    build_configuration_manager_surface,
)
from atlanticus.web.compositions.users_manager import (
    UsersManagerDraftValidationWorkflow,
    UsersManagerSourceWorkflow,
)
from atlanticus.web.manager import ManagerPrincipal, ManagerSurface
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceSnapshot


class SourceStub:
    def __init__(self, source_key: str) -> None:
        self.source_key = SourceKey(source_key)

    def get_current(self) -> SourceSnapshot:
        return SourceSnapshot(self.source_key, None, None)


class UsersAdministrationStub:
    def load_current(self):
        return SimpleNamespace(configuration=None, source_snapshot=SourceSnapshot(SourceKey('users'), None, None))


class ProjectionStub:
    pass


def dependencies() -> ConfigurationManagerDependencies:
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        is_local=True,
    )
    return ConfigurationManagerDependencies(
        users_source_key=SourceKey('users'),
        users_profiles_administration=UsersAdministrationStub(),
        users_projection=ProjectionStub(),
        navigation_source=SourceStub('navigation'),
        navigation_projection=ProjectionStub(),
        tools_source=SourceStub('tools'),
        tools_projection=ProjectionStub(),
        principal_provider=lambda: principal,
    )


def test_surface_uses_generic_manager_contract_for_all_base_modules() -> None:
    definition = build_configuration_manager_surface(dependencies())
    surface = ManagerSurface(definition)

    assert definition.route_prefix == MANAGER_ROUTE_PREFIX == '/manager'
    assert tuple(module.key for module in surface.registry.modules) == (
        'users',
        'navigation',
        'tools',
    )

    users, navigation, tools = definition.modules
    assert users.source_key == SourceKey('users')
    assert users.source_service == USERS_SOURCE_SERVICE
    assert users.source_reader_service == USERS_SOURCE_READER_SERVICE
    assert users.source_history_service == USERS_SOURCE_HISTORY_SERVICE
    assert users.projection_service == USERS_PROJECTION_SERVICE
    assert users.draft_validation_service == USERS_DRAFT_VALIDATION_SERVICE

    assert navigation.source_key == SourceKey('navigation')
    assert navigation.source_service == NAVIGATION_SOURCE_SERVICE
    assert navigation.source_reader_service == NAVIGATION_SOURCE_READER_SERVICE
    assert navigation.source_history_service == NAVIGATION_SOURCE_HISTORY_SERVICE
    assert navigation.projection_service == NAVIGATION_PROJECTION_SERVICE
    assert navigation.draft_validation_service == NAVIGATION_DRAFT_VALIDATION_SERVICE

    assert tools.source_key == SourceKey('tools')
    assert tools.source_service == TOOLS_SOURCE_SERVICE
    assert tools.source_reader_service == TOOLS_SOURCE_READER_SERVICE
    assert tools.source_history_service == TOOLS_SOURCE_HISTORY_SERVICE
    assert tools.projection_service == TOOLS_PROJECTION_SERVICE
    assert tools.draft_validation_service == TOOLS_DRAFT_VALIDATION_SERVICE


def test_service_module_registers_separate_generic_capabilities() -> None:
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

    users_source = services.require(USERS_SOURCE_SERVICE)
    assert isinstance(users_source, UsersManagerSourceWorkflow)
    assert services.require(USERS_SOURCE_READER_SERVICE) is users_source
    assert services.require(USERS_SOURCE_HISTORY_SERVICE) is users_source
    assert isinstance(
        services.require(USERS_DRAFT_VALIDATION_SERVICE),
        UsersManagerDraftValidationWorkflow,
    )
    assert services.require(USERS_PROJECTION_SERVICE) is injected.users_projection

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
