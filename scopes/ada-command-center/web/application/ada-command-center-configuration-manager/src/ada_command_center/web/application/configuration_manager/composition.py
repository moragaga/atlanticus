from __future__ import annotations

from ada_command_center.domain.alarms.identity import (
    ALARM_CONFIGURATION_SOURCE_KEY as ALARM_CONFIGURATION_SOURCE_KEY_VALUE,
)
from ada_command_center.web.alarms.configuration.manager import (
    compose_alarm_configuration_manager,
)
from ada_command_center.web.application.configuration_manager.administration import (
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada_command_center.web.tools.catalog_manager import create_tool_catalog_manager_entry
from atlanticus.web.bootstrap import create_bootstrap_web_module
from atlanticus.web.manager import ManagerModuleGroup, ManagerSurfaceDefinition
from atlanticus.web.navigation.configuration import NAVIGATION_SOURCE_KEY
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
    tool_catalog_entry = (
        create_tool_catalog_manager_entry(
            manager=dependencies.tool_catalog_manager,
            principal_provider=dependencies.principal_provider,
            group_key='configuration',
        )
        if dependencies.tool_catalog_manager is not None
        else None
    )
    administration = dependencies.administration
    groups = (
        (ManagerModuleGroup(key='administration', title='Administración', order=5),)
        if administration is not None
        else ()
    )
    modules = (
        (administration.profiles_module, administration.navigation_module)
        if administration is not None
        else ()
    )
    administration_entries = (
        (
            administration.users_entry,
            *((administration.users_projection_entry,) if administration.users_projection_entry else ()),
        )
        if administration is not None
        else ()
    )
    return ManagerSurfaceDefinition(
        principal_provider=dependencies.principal_provider,
        groups=(*groups, ManagerModuleGroup(key='configuration', title='Configuraciones', order=10)),
        modules=(*modules, alarm_configuration.module),
        entries=(
            *administration_entries,
            *((tool_catalog_entry,) if tool_catalog_entry is not None else ()),
        ),
        route_prefix=MANAGER_ROUTE_PREFIX,
        web_modules=(create_bootstrap_web_module(),),
    )


__all__ = [
    'ALARM_CONFIGURATION_MANAGER_ACCESS_KEY',
    'ALARM_CONFIGURATION_SOURCE_KEY',
    'MANAGER_ROUTE_PREFIX',
    'NAVIGATION_MANAGER_ACCESS_KEY',
    'NAVIGATION_SOURCE_KEY',
    'PROFILES_MANAGER_ACCESS_KEY',
    'USERS_MANAGER_ACCESS_KEY',
    'build_configuration_manager_surface',
]
