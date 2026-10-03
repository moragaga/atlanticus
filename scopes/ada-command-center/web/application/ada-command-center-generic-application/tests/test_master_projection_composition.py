from pathlib import Path

from ada_command_center.web.application.configuration_manager.composition import (
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    CommandCenterAdministrationDependencies,
    ConfigurationManagerDependencies,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersRuntimeStore,
)
from ada_command_center.web.application.generic.master_projection.composition import (
    compose_command_center_master_projection_backend,
)
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.master_projection.plan import ProjectionPlanState, UsersPlanState
from atlanticus.web.navigation.configuration import NAVIGATION_SOURCE_KEY
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def _dependencies(source):
    administration = CommandCenterAdministrationDependencies(
        profiles_module=None,
        navigation_module=None,
        users_entry=None,
        profiles_projection_store=InProcessProjectionStore(),
        navigation_projection_store=InProcessProjectionStore(),
        users_runtime_store=InProcessUsersRuntimeStore(),
    )
    return ConfigurationManagerDependencies(
        source_store=source,
        projection_store=InProcessProjectionStore(),
        principal_provider=lambda: None,
        administration=administration,
    )


def test_command_center_master_projection_uses_existing_manager_domains(tmp_path: Path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'sources'))
    backend = compose_command_center_master_projection_backend(_dependencies(source))
    plan = backend.planner.inspect()

    assert {entry.key for entry in plan.entries} == {
        PROFILES_CONFIGURATION_SOURCE_KEY,
        NAVIGATION_SOURCE_KEY,
        ALARM_CONFIGURATION_SOURCE_KEY,
    }
    assert all(entry.state is ProjectionPlanState.SOURCE_MISSING for entry in plan.entries)
    assert plan.users.state is UsersPlanState.CATALOG_UNAVAILABLE
