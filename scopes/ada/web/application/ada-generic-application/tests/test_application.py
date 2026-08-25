from __future__ import annotations

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)


def test_definition_composes_minimum_ada_web_capabilities() -> None:
    definition = create_application_definition()

    assert definition.metadata.application_id == 'ada-generic-application'
    assert definition.metadata.display_name == 'ADA'
    assert tuple(module.name for module in definition.modules) == ('identity', 'navigation')
    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_runtime_starts_locally_without_external_infrastructure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime()
    client = runtime.server.test_client()

    assert runtime.environment.value == 'local'
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    assert client.get('/').status_code == 200
    assert client.get('/_dash-layout').status_code == 200
    assert runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)

    provider = runtime.services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )
    navigation = provider.current()
    assert navigation.home_route_key == 'home'
    assert navigation.find_link('home').href == '/'

    with client.session_transaction() as session:
        snapshot = session['_atlanticus_access_snapshot']
    assert snapshot['identity']['subject_id'] == 'local:test-user'


def test_public_package_exposes_runtime_factory() -> None:
    from ada.web.application.generic import create_application_runtime

    assert callable(create_application_runtime)
