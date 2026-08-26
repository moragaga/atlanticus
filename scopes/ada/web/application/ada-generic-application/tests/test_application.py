from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.ui.branding import ADA_BRANDING_ASSET_LAYER
from ada.web.ui.core import ADA_UI_ASSET_LAYER
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)


def test_definition_composes_minimum_ada_web_capabilities() -> None:
    definition = create_application_definition()

    assert definition.metadata.application_id == 'ada-generic-application'
    assert definition.metadata.display_name == 'ADA'
    assert definition.metadata.version == '0.1.2'
    assert tuple(module.name for module in definition.modules) == (
        'ada-ui',
        'ada-branding',
        'identity',
        'navigation',
    )
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
    assert any(
        entry.startswith(f'{ADA_UI_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_BRANDING_ASSET_LAYER.target_name}/css/')
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


def test_configured_tool_name_is_injected_into_operational_brand(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(tool_display_name='Operaciones Integradas')
    layout = runtime.dash.layout()

    brand = _require_by_class(layout, 'ada-operational-brand')
    context = _require_by_class(brand, 'ada-operational-brand__context')
    assert 'Operaciones Integradas' in _text_content(context)


def test_public_package_exposes_runtime_factory() -> None:
    from ada.web.application.generic import create_application_runtime

    assert callable(create_application_runtime)


def _require_by_class(component: Component, class_name: str) -> Component:
    result = _find_by_class(component, class_name)
    if result is None:
        raise AssertionError(f'Component with class {class_name!r} was not found')
    return result


def _find_by_class(component: Component, class_name: str) -> Component | None:
    classes = getattr(component, 'className', '') or ''
    if class_name in classes.split():
        return component
    for child in _children(component):
        result = _find_by_class(child, class_name)
        if result is not None:
            return result
    return None


def _children(component: Component) -> list[Component]:
    children = getattr(component, 'children', None)
    if children is None:
        return []
    if not isinstance(children, (list, tuple)):
        children = [children]
    return [child for child in children if isinstance(child, Component)]


def _text_content(component: Component) -> str:
    children = getattr(component, 'children', None)
    if isinstance(children, str):
        return children
    if children is None:
        return ''
    if not isinstance(children, (list, tuple)):
        children = [children]
    return ''.join(
        child if isinstance(child, str) else _text_content(child)
        for child in children
        if isinstance(child, (str, Component))
    )
