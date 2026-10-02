from __future__ import annotations

from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersAdministrationStore,
    InProcessUsersRegistryStore,
)
from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.application.generic.master_projection.composition import (
    compose_master_projection_planner,
)
from ada.web.application.generic.master_projection.plan import (
    ProjectionPlanState,
    UsersPlanState,
)
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def test_web_backend_reuses_six_projectors_and_does_not_require_manager_permissions(tmp_path):
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'sources'))
    stores = ConfigurationManagerStores(
        navigation_source=source,
        tools_source=source,
        access_source=source,
        profiles_source=source,
        kpi_registry_source=source,
        kpi_definitions_source=source,
        navigation=InProcessProjectionStore(),
        tools=InProcessProjectionStore(),
        access=InProcessProjectionStore(),
        profiles=InProcessProjectionStore(),
        kpi_registry=InProcessProjectionStore(),
        kpi_definitions=InProcessProjectionStore(),
        users_registry=InProcessUsersRegistryStore(),
        users_promoted=InProcessUsersAdministrationStore(),
        users_recovery=lambda: None,
        users_snapshot_ids=lambda: ('approved-1',),
    )
    planner = compose_master_projection_planner(stores)
    report = planner.inspect()
    assert {item.key.value for item in report.entries} == {
        'navigation',
        'profiles-configuration',
        'tools',
        'ada-access',
        'kpis',
        'kpi-definitions',
    }
    assert {item.key.value for item in report.entries if item.prerequisites} == {
        'ada-access',
        'kpis',
        'kpi-definitions',
    }
    assert all(item.state is ProjectionPlanState.SOURCE_MISSING for item in report.entries)
    assert report.users.state is UsersPlanState.PROFILES_PENDING
    assert report.ready == ()
