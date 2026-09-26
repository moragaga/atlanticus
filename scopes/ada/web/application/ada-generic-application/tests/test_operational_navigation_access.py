from dataclasses import replace

import pytest

from ada.web.application.generic.composition import (
    create_local_operational_composition,
    create_operational_navigation_modules,
)
from ada.web.application.generic.navigation_binding import (
    manager_navigation_principal,
    public_navigation_principal,
)
from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationLinkDefinition,
    NavigationPrincipalProvider,
    can_access_navigation_path,
    resolve_navigation,
)


def _manager(profile: str | None, *, local: bool = False) -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='known-subject',
        display_name='Known User',
        profile_keys=() if profile is None else (profile,),
        is_local=local,
    )


def _definition() -> NavigationDefinition:
    return NavigationDefinition(
        links=(
            NavigationLinkDefinition(key='public', label='Public', href='/public'),
            NavigationLinkDefinition(
                key='restricted', label='Restricted', href='/restricted',
                allowed_profiles=('basic',),
            ),
            NavigationLinkDefinition(
                key='disabled', label='Disabled', href='/disabled', enabled=False,
            ),
        )
    )


@pytest.mark.parametrize(
    ('profile', 'local', 'expected'),
    [
        ('root', False, True),
        ('local', True, True),
        ('local', False, False),
        ('root', True, False),
        ('basic', False, False),
        (None, False, False),
    ],
)
def test_manager_navigation_requires_an_attested_privileged_context(
    profile: str | None, local: bool, expected: bool
) -> None:
    principal = manager_navigation_principal(_manager(profile, local=local), allow_local=True)

    assert principal.administrative_override is expected
    assert can_access_navigation_path(
        _definition(), principal=principal, pathname='/disabled'
    ) is expected
    assert can_access_navigation_path(
        _definition(), principal=principal, pathname='/manager'
    ) is expected


def test_local_recovery_is_never_implicit() -> None:
    principal = manager_navigation_principal(_manager('local', local=True))
    assert not principal.administrative_override


def test_anonymous_navigation_is_independent_of_identity() -> None:
    principal = public_navigation_principal()
    menu = resolve_navigation(_definition(), principal=principal)

    assert principal.access_key is None
    assert not principal.administrative_override
    assert tuple(link.key for link in menu.links) == ('public',)
    assert can_access_navigation_path(_definition(), principal=principal, pathname='/')
    assert not can_access_navigation_path(_definition(), principal=principal, pathname='/restricted')


def test_operational_application_can_mount_navigation_without_identity(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)

    runtime = create_application_runtime(composition=create_local_operational_composition())

    assert not runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert runtime.server.test_client().get('/', headers={'Accept': 'text/html'}).status_code == 200
    denied = runtime.server.test_client().get(
        '/not-published', headers={'Accept': 'text/html'}
    )
    assert denied.status_code == 403


def test_operational_authorization_consumes_injected_profiles_without_identity(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    definition = _definition()
    principal = manager_navigation_principal(_manager('basic'))
    modules = create_operational_navigation_modules(
        definition_provider=NavigationDefinitionProvider(lambda: definition),
        principal_provider=NavigationPrincipalProvider(lambda: principal),
    )
    baseline = create_local_operational_composition()
    replacements = {module.name: module for module in modules}
    composition = replace(
        baseline,
        modules=tuple(replacements.get(module.name, module) for module in baseline.modules),
    )
    runtime = create_application_runtime(composition=composition)
    client = runtime.server.test_client()

    assert client.get('/public', headers={'Accept': 'text/html'}).status_code == 200
    assert client.get('/restricted', headers={'Accept': 'text/html'}).status_code == 200
    assert client.get('/disabled', headers={'Accept': 'text/html'}).status_code == 403
    assert client.get('/manager', headers={'Accept': 'text/html'}).status_code == 403
