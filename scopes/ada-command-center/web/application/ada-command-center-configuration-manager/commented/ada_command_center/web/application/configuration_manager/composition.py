# La composición monta un único módulo real dentro de la superficie Manager genérica.
# El SourceKey y el access key pertenecen al host temporal y no cambian AlarmConfiguration.
from __future__ import annotations

from ada_command_center.web.alarms.configuration.manager import (
    compose_alarm_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from atlanticus.web.bootstrap import create_bootstrap_web_module
from atlanticus.web.manager import ManagerModuleGroup, ManagerSurfaceDefinition
from atlanticus.web.source.models import SourceKey

MANAGER_ROUTE_PREFIX = '/manager'
ALARM_CONFIGURATION_MANAGER_ACCESS_KEY = 'alarms.manage'
ALARM_CONFIGURATION_SOURCE_KEY = SourceKey('alarm-configuration')


def build_configuration_manager_surface(
    dependencies: ConfigurationManagerDependencies,
) -> ManagerSurfaceDefinition:
    alarm_configuration = compose_alarm_configuration_manager(
        source_store=dependencies.source_store,
        projection_store=dependencies.projection_store,
        principal_provider=dependencies.principal_provider,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        group_key='configuration',
        access_key=ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,
        tool_reference_reader=dependencies.tool_reference_reader,
        title='Configuración de alarmas',
        description='Administra las reglas y mensajes del Centro de Control.',
        source_name=dependencies.source_name,
        projection_name=dependencies.projection_name,
    )
    return ManagerSurfaceDefinition(
        principal_provider=dependencies.principal_provider,
        groups=(
            ManagerModuleGroup(
                key='configuration',
                title='Configuraciones',
                order=10,
            ),
        ),
        modules=(alarm_configuration.module,),
        route_prefix=MANAGER_ROUTE_PREFIX,
        web_modules=(create_bootstrap_web_module(),),
    )
