from __future__ import annotations

import json

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.composition import AdaApplicationComposition
from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import (
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    create_navigation_module,
)


def _navigation_only_composition() -> AdaApplicationComposition:
    navigation = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='home',
                label='Inicio',
                href='/',
                order=0,
            ),
        ),
        home_route_key='home',
    )
    principal = NavigationPrincipal(
        access_key='local',
        unrestricted=True,
        user=NavigationUser(
            display_name='Local User',
            profile_key='local',
            profile_label='Local',
            profile_background_color='#3778C2',
            profile_text_color='#FFFFFF',
            avatar_text='LU',
        ),
    )
    return AdaApplicationComposition(
        modules=(
            create_navigation_module(
                navigation,
                principal_provider=NavigationPrincipalProvider(lambda: principal),
            ),
        )
    )


def test_explicit_composition_replaces_canonical_operational_modules() -> None:
    definition = create_application_definition(composition=_navigation_only_composition())

    assert tuple(module.name for module in definition.modules) == ('navigation',)
    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_application_runtime_can_mount_without_identity_when_composition_does_not_request_it(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_application_runtime(composition=_navigation_only_composition())
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert runtime.dash.server is runtime.server
    assert not runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
    assert 'Local User' in payload
    assert 'ada-navigation-offcanvas' in payload


def test_composition_can_replace_page_packages_without_application_branching() -> None:
    composition = _navigation_only_composition()
    definition = create_application_definition(
        composition=AdaApplicationComposition(
            modules=composition.modules,
            page_packages=('ada.web.application.generic.pages',),
        )
    )

    assert definition.page_packages == ('ada.web.application.generic.pages',)
