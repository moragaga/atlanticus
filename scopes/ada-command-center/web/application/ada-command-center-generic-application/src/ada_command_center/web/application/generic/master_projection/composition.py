from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.web.alarms.configuration import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.application.configuration_manager.administration import (
    NAVIGATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.composition import (
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.master_projection.apply import MasterProjectionExecutor
from atlanticus.web.master_projection.plan import MasterProjectionPlanner, ProjectionDomain
from atlanticus.web.navigation.configuration import create_navigation_projection_service
from atlanticus.web.profiles.configuration.source_projection import (
    create_profiles_projection_service,
)


@dataclass(frozen=True, slots=True)
class CommandCenterMasterProjectionBackend:
    planner: MasterProjectionPlanner
    executor: MasterProjectionExecutor


def compose_command_center_master_projection_backend(
    dependencies: ConfigurationManagerDependencies,
) -> CommandCenterMasterProjectionBackend:
    if not isinstance(dependencies, ConfigurationManagerDependencies):
        raise TypeError('Command Center Master Projection dependencies are invalid')
    administration = dependencies.administration
    if administration is None:
        raise ValueError('Command Center Master Projection requires administration dependencies')
    domains = (
        ProjectionDomain(
            key=PROFILES_CONFIGURATION_SOURCE_KEY,
            source=dependencies.source_store,
            projection=administration.profiles_projection_store,
            service=create_profiles_projection_service(
                source=dependencies.source_store,
                projection=administration.profiles_projection_store,
            ),
        ),
        ProjectionDomain(
            key=NAVIGATION_SOURCE_KEY,
            source=dependencies.source_store,
            projection=administration.navigation_projection_store,
            service=create_navigation_projection_service(
                source=dependencies.source_store,
                projection=administration.navigation_projection_store,
            ),
        ),
        ProjectionDomain(
            key=ALARM_CONFIGURATION_SOURCE_KEY,
            source=dependencies.source_store,
            projection=dependencies.projection_store,
            service=create_alarm_configuration_projection_service(
                source=dependencies.source_store,
                projection=dependencies.projection_store,
            ),
        ),
    )
    planner = MasterProjectionPlanner(
        domains=domains,
        profiles_key=PROFILES_CONFIGURATION_SOURCE_KEY,
    )
    return CommandCenterMasterProjectionBackend(
        planner=planner,
        executor=MasterProjectionExecutor(planner=planner, domains=domains),
    )
