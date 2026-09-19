import pytest

pytest.importorskip('dash')
pytest.importorskip('dash_bootstrap_components')

from atlanticus.web.compositions.profiles_manager import (
    PROFILES_MANAGER_PROJECTION_SERVICE,
    PROFILES_MANAGER_SOURCE_SERVICE,
    PROFILES_MANAGER_VALIDATION_SERVICE,
    compose_profiles_manager,
)
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.profiles.projection.local import (
    LocalProfilesProjectionStore,
    LocalProfilesProjectionStoreSettings,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='tester',
        display_name='Tester',
        access_keys=('profiles.manage',),
        is_local=True,
    )


def test_profiles_manager_registers_generic_source_projection_contract(tmp_path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalProfilesProjectionStore(
        LocalProfilesProjectionStoreSettings(root=tmp_path / 'projection')
    )

    composition = compose_profiles_manager(
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
        access_key='profiles.manage',
    )

    module = composition.module
    services = ServiceRegistry()
    assert module.web_module is not None
    assert module.web_module.register_services is not None
    module.web_module.register_services(services)

    assert module.key == 'profiles'
    assert module.route == '/profiles'
    assert module.source_service == PROFILES_MANAGER_SOURCE_SERVICE
    assert module.source_reader_service == PROFILES_MANAGER_SOURCE_SERVICE
    assert module.source_history_service == PROFILES_MANAGER_SOURCE_SERVICE
    assert module.projection_service == PROFILES_MANAGER_PROJECTION_SERVICE
    assert module.draft_validation_service == PROFILES_MANAGER_VALIDATION_SERVICE
    assert module.access_key == 'profiles.manage'
    assert module.source_name == 'Profiles Source'
    assert module.projection_name == 'Profiles Projection'
    assert services.require(PROFILES_MANAGER_SOURCE_SERVICE) is composition.source_workflow
    assert services.require(PROFILES_MANAGER_PROJECTION_SERVICE) is composition.projection_service
    assert services.require(PROFILES_MANAGER_VALIDATION_SERVICE) is composition.validation_workflow


def test_profiles_manager_web_context_uses_users_local_identity_definitions(tmp_path) -> None:
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projection = LocalProfilesProjectionStore(
        LocalProfilesProjectionStoreSettings(root=tmp_path / 'projection')
    )

    composition = compose_profiles_manager(
        source_store=source,
        projection_store=projection,
        principal_provider=_principal,
        group_key='configuration',
        access_key='profiles.manage',
    )

    services = ServiceRegistry()
    rendered = composition.module.layout(services)
    text = str(rendered)

    assert 'Jane Doe' in text
    assert 'John Doe' in text
    assert '#C85D91' in text
    assert '#3778C2' in text
