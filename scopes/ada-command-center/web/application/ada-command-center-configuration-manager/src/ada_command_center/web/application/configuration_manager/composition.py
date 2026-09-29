from __future__ import annotations

from ada_command_center.domain.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY as ALARM_CONFIGURATION_SOURCE_KEY_VALUE,
)
from ada_command_center.web.alarms.configuration.manager import (
    compose_alarm_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada_command_center.web.tools.catalog_manager import (
    create_tool_catalog_manager_entry,
)
from atlanticus.web.bootstrap import create_bootstrap_web_module
from atlanticus.web.manager import ManagerModuleGroup, ManagerSurfaceDefinition
from atlanticus.web.source.models import SourceKey

MANAGER_ROUTE_PREFIX = '/manager'
ALARM_CONFIGURATION_MANAGER_ACCESS_KEY = 'alarms.manage'
ALARM_CONFIGURATION_SOURCE_KEY = SourceKey(ALARM_CONFIGURATION_SOURCE_KEY_VALUE)


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
    entry = (
        create_tool_catalog_manager_entry(
            manager=dependencies.tool_catalog_manager,
            principal_provider=dependencies.principal_provider,
            group_key='configuration',
        )
        if dependencies.tool_catalog_manager is not None
        else None
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
        entries=(entry,) if entry is not None else (),
        route_prefix=MANAGER_ROUTE_PREFIX,
        web_modules=(create_bootstrap_web_module(),),
    )
