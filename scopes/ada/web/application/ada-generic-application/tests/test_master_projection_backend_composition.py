from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    InProcessProjectionStore,
    InProcessUsersAdministrationStore,
    InProcessUsersRegistryStore,
)
from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.application.generic.master_projection.composition import (
    compose_master_projection_backend,
    compose_master_projection_planner,
)
from atlanticus.web.master_projection.apply import MasterApplyError
from atlanticus.web.master_projection.plan import ProjectionPlanState
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def test_backend_composes_six_existing_services_without_replacing_preview(tmp_path):
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
    )
    backend = compose_master_projection_backend(stores)
    expected = {
        'navigation',
        'profiles-configuration',
        'tools',
        'ada-access',
        'kpis',
        'kpi-definitions',
    }
    plan = backend.planner.inspect()
    assert {item.key.value for item in plan.entries} == expected
    assert all(item.state is ProjectionPlanState.SOURCE_MISSING for item in plan.entries)
    assert {
        item.key.value for item in compose_master_projection_planner(stores).inspect().entries
    } == expected
    users_key = SourceKey('users')
    fake_target = ProjectionTarget(
        users_key,
        SourceReleaseRef(SourceReleaseId('users-1'), datetime(2026, 9, 28, tzinfo=UTC)),
    )
    with pytest.raises(MasterApplyError) as raised:
        backend.executor.apply(source_key=users_key, expected_target=fake_target)
    assert raised.value.reason == 'INVALID_SELECTION'
