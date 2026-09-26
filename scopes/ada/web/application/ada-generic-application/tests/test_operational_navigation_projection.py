from datetime import UTC, datetime

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.configuration_manager.wiring import NAVIGATION_SOURCE_KEY
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceReleaseId


def _settings(tmp_path):
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_TOOL_NAMESPACE': 'navigation-test',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path / 'tool'),
        }
    )


def _projection():
    now = datetime(2026, 9, 25, tzinfo=UTC)
    return ProjectionRecord(
        source_key=NAVIGATION_SOURCE_KEY,
        source_release_id=SourceReleaseId('navigation-test-release'),
        source_published_at_utc=now,
        projected_at_utc=now,
        payload=NavigationConfigurationCatalog(
            links=(
                NavigationLinkConfiguration(
                    key='public', label='Public', href='/public',
                ),
                NavigationLinkConfiguration(
                    key='disabled', label='Disabled', href='/disabled', enabled=False,
                ),
            ),
        ),
    )


def test_local_bootstrap_can_recover_manager_then_consume_new_projection(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    runtime = create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:jane-doe'),
    )
    client = runtime.server.test_client()
    html_headers = {'Accept': 'text/html'}

    assert client.get('/manager', headers=html_headers).status_code == 200
    assert client.get('/disabled', headers=html_headers).status_code == 200
    stores.navigation.replace_active(_projection())
    assert client.get('/public', headers=html_headers).status_code == 200
    assert client.get('/disabled', headers=html_headers).status_code == 200
    assert client.get('/manager/navigation', headers=html_headers).status_code == 200


def test_unknown_local_subject_does_not_gain_recovery_permission(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    runtime = create_operational_application_runtime(
        settings=_settings(tmp_path),
        manager_stores=stores,
        identity_provider=LocalIdentityProvider(subject_id='local:unknown'),
    )
    client = runtime.server.test_client()
    html_headers = {'Accept': 'text/html'}

    assert client.get('/').status_code == 200
    assert client.get('/manager', headers=html_headers).status_code == 403
    stores.navigation.replace_active(_projection())
    assert client.get('/public', headers=html_headers).status_code == 200
    assert client.get('/disabled', headers=html_headers).status_code == 403
