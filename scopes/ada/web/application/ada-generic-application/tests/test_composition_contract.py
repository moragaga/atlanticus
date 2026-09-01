from __future__ import annotations

import json

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_ada_alarm_surface_modules,
    create_ada_branding_modules,
    create_ada_operational_shell_modules,
    create_ada_runtime_experience_modules,
    create_ada_shared_ui_modules,
    create_identity_navigation_modules,
    create_local_identity_modules,
    create_local_operational_composition,
)
from ada.web.application.generic.layout import (
    build_body_application_layout,
    create_ada_operational_layout,
)
from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY


def _body_only_composition() -> AdaApplicationComposition:
    return AdaApplicationComposition(
        modules=(),
        layout=build_body_application_layout,
    )


def _operational_without_navigation_composition() -> AdaApplicationComposition:
    return AdaApplicationComposition(
        modules=(
            *create_ada_shared_ui_modules(),
            *create_ada_alarm_surface_modules(),
            *create_ada_branding_modules(),
            *create_ada_operational_shell_modules(include_navigation=False),
        ),
        layout=create_ada_operational_layout(navigation_enabled=False),
    )


def test_explicit_composition_replaces_canonical_operational_modules() -> None:
    definition = create_application_definition(composition=_body_only_composition())

    assert definition.modules == ()
    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_application_runtime_can_mount_with_no_optional_capabilities(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_application_runtime(composition=_body_only_composition())
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert runtime.dash.server is runtime.server
    assert not runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert not runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
    assert 'ada-application-content' in payload
    assert 'operational_header' not in payload
    assert 'ada-navigation-offcanvas' not in payload


def test_ada_operational_shell_can_mount_without_identity_or_navigation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_application_runtime(composition=_operational_without_navigation_composition())
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert not runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert not runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
    assert 'operational_header' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert 'ada-navigation-desktop-toggle' not in payload
    assert 'ada-navigation-mobile-toggle' not in payload
    assert 'ada-navigation-offcanvas' not in payload


def test_local_operational_composition_is_built_from_explicit_responsibility_blocks() -> None:
    composition = create_local_operational_composition()

    assert tuple(module.name for module in create_ada_shared_ui_modules()) == (
        'ada-ui',
        'ada-display-status',
        'ada-global-indicator',
    )
    assert tuple(module.name for module in create_ada_alarm_surface_modules()) == (
        'ada-alarm-management-summary',
        'ada-alarm-status',
    )
    assert tuple(module.name for module in create_ada_branding_modules()) == ('ada-branding',)
    assert tuple(module.name for module in create_local_identity_modules()) == ('identity',)
    assert tuple(module.name for module in create_identity_navigation_modules()) == ('navigation',)
    assert tuple(
        module.name for module in create_ada_operational_shell_modules(include_navigation=True)
    ) == ('ada-navigation', 'ada-operational-header')
    assert tuple(module.name for module in create_ada_runtime_experience_modules()) == (
        'ada-session',
        'ada-wake-lock',
        'ada-page-readiness',
    )
    assert tuple(module.name for module in composition.modules) == (
        'ada-ui',
        'ada-display-status',
        'ada-global-indicator',
        'ada-alarm-management-summary',
        'ada-alarm-status',
        'ada-branding',
        'identity',
        'navigation',
        'ada-navigation',
        'ada-operational-header',
        'ada-session',
        'ada-wake-lock',
        'ada-page-readiness',
    )


def test_composition_can_replace_page_packages_without_application_branching() -> None:
    definition = create_application_definition(
        composition=AdaApplicationComposition(
            modules=(),
            layout=build_body_application_layout,
            page_packages=('ada.web.application.generic.pages',),
        )
    )

    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_legacy_layout_entrypoint_is_not_preserved() -> None:
    from ada.web.application.generic import layout

    assert not hasattr(layout, 'build_application_layout')
