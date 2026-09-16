import pytest

pytest.importorskip('dash')

from atlanticus.web.compositions.navigation_manager import (
    NAVIGATION_MANAGER_PROJECTION_SERVICE,
    NAVIGATION_MANAGER_SOURCE_SERVICE,
    NAVIGATION_MANAGER_VALIDATION_SERVICE,
    compose_navigation_manager,
)
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.navigation.projection.local import (
    LocalNavigationProjectionStore,
    LocalNavigationProjectionStoreSettings,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='tester',
        display_name='Tester',
        is_local=True,
    )


def test_navigation_manager_registers_one_generic_source_route(tmp_path) -> None:
    services = ServiceRegistry()
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalNavigationProjectionStore(
        LocalNavigationProjectionStoreSettings(root=tmp_path / 'projection')
    )

    composition = compose_navigation_manager(
        services=services,
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
    )

    module = composition.module
    assert module.source_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.source_reader_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.source_history_service == NAVIGATION_MANAGER_SOURCE_SERVICE
    assert module.projection_service == NAVIGATION_MANAGER_PROJECTION_SERVICE
    assert module.draft_validation_service == NAVIGATION_MANAGER_VALIDATION_SERVICE
    assert services.require(NAVIGATION_MANAGER_SOURCE_SERVICE) is composition.source_workflow
    assert services.require(NAVIGATION_MANAGER_PROJECTION_SERVICE) is composition.projection_service
    assert services.require(NAVIGATION_MANAGER_VALIDATION_SERVICE) is composition.validation_workflow
