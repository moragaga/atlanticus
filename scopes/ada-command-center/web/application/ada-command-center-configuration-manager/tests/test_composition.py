from ada_command_center.web.alarms.configuration.manager import (
    ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE,
    ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE,
    ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE,
)
from ada_command_center.web.application.configuration_manager import (
    ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,
    ALARM_CONFIGURATION_SOURCE_KEY,
    MANAGER_ROUTE_PREFIX,
    ConfigurationManagerDependencies,
    build_configuration_manager_surface,
)
from atlanticus.web.manager import ManagerPrincipal, ManagerSurface
from atlanticus.web.services import ServiceRegistry


class SourceStoreStub:
    pass


class ProjectionStoreStub:
    pass


def dependencies() -> ConfigurationManagerDependencies:
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        access_keys=(ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,),
        is_local=True,
    )
    return ConfigurationManagerDependencies(
        source_store=SourceStoreStub(),
        projection_store=ProjectionStoreStub(),
        principal_provider=lambda: principal,
        source_name='Local Source',
        projection_name='In-process Projection',
    )


def test_surface_mounts_only_alarm_configuration_manager_module() -> None:
    definition = build_configuration_manager_surface(dependencies())
    surface = ManagerSurface(definition)

    assert definition.route_prefix == MANAGER_ROUTE_PREFIX == '/manager'
    assert tuple(group.key for group in definition.groups) == ('configuration',)
    assert tuple(module.key for module in definition.modules) == ('alarm-configuration',)

    module = definition.modules[0]
    assert module.source_key == ALARM_CONFIGURATION_SOURCE_KEY
    assert module.access_key == ALARM_CONFIGURATION_MANAGER_ACCESS_KEY
    assert module.source_name == 'Local Source'
    assert module.projection_name == 'In-process Projection'
    assert surface.registry.route_for(module) == '/manager/alarm-configuration'


def test_alarm_configuration_module_registers_real_workflows() -> None:
    definition = build_configuration_manager_surface(dependencies())
    module = definition.modules[0]
    services = ServiceRegistry()

    assert module.web_module is not None
    assert module.web_module.register_services is not None
    module.web_module.register_services(services)

    assert services.contains(ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE)
    assert services.contains(ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE)
    assert services.contains(ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE)
