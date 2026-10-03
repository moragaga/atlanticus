from dataclasses import replace

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.master_projection.composition import (
    compose_master_projection_planner,
)
from atlanticus.web.master_projection.plan import ProjectionPlanState, UsersPlanState


def test_master_projection_keeps_six_source_domains_and_users_is_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    stores = replace(
        stores,
        users_recovery=lambda: None,
        users_snapshot_ids=lambda: ('snapshot-1',),
    )
    report = compose_master_projection_planner(stores).inspect()
    assert {item.key.value for item in report.entries} == {
        'navigation',
        'profiles-configuration',
        'tools',
        'ada-access',
        'kpi-registry',
        'kpi-definitions',
    }
    assert all(item.state is ProjectionPlanState.SOURCE_MISSING for item in report.entries)
    assert report.users.state is UsersPlanState.SNAPSHOT_SELECTION_REQUIRED
    assert report.users.executable is True
