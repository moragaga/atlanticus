from __future__ import annotations

import json

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.shell.navigation import ADA_NAVIGATION_ASSET_LAYER, AdaNavigationView
from ada.web.ui.branding import (
    ADA_BRANDING_ASSET_LAYER,
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
)
from ada.web.ui.core import ADA_UI_ASSET_LAYER
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)


def test_definition_composes_current_ada_web_capabilities() -> None:
    definition = create_application_definition()

    assert definition.metadata.application_id == 'ada-generic-application'
    assert definition.metadata.display_name == 'ADA'
    assert definition.metadata.version == '0.1.5'
    assert tuple(module.name for module in definition.modules) == (
        'ada-ui',
        'ada-branding',
        'identity',
        'navigation',
        'ada-navigation',
    )
    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_runtime_starts_locally_with_real_navigation_presentation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime()
    client = runtime.server.test_client()

    assert runtime.environment.value == 'local'
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    assert client.get('/').status_code == 200
    layout_response = client.get('/_dash-layout')
    assert layout_response.status_code == 200
    payload = json.dumps(layout_response.get_json(), ensure_ascii=False)
    assert 'ada-navigation-desktop-toggle' in payload
    assert 'ada-navigation-mobile-toggle' in payload
    assert 'ada-navigation-offcanvas' in payload
    assert 'Test User' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert DEFAULT_OPERATIONAL_BRAND_LOGO_SRC in payload
    assert DEFAULT_PELAMBRES_BRAND_LOGO_SRC in payload
    assert 'Versión 0.1.5' in payload
    assert runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
    assert any(
        entry.startswith(f'{ADA_UI_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_BRANDING_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_NAVIGATION_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )

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


def test_tool_name_and_navigation_view_are_injected_without_shell_hardcoding(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(
        tool_display_name='Operaciones Integradas',
        navigation_view=AdaNavigationView(
            title='ADA',
            subtitle='Navegación de la herramienta',
        ),
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'Operaciones Integradas' in payload
    assert 'Navegación de la herramienta' in payload


def test_public_package_exposes_runtime_factory() -> None:
    from ada.web.application.generic import create_application_runtime

    assert callable(create_application_runtime)
