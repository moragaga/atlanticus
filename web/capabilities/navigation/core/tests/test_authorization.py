import pytest
from flask import Flask

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    can_access_navigation_path,
    create_navigation_authorization_module,
    create_navigation_module,
    resolve_navigation_route,
)
from atlanticus.web.services import ServiceRegistry


def _principal(profile: str, *, unrestricted: bool = False) -> NavigationPrincipal:
    return NavigationPrincipal(
        access_key=profile,
        unrestricted=unrestricted,
        user=NavigationUser(
            display_name='User',
            profile_key=profile,
            profile_label=profile.title(),
            profile_background_color='#123456',
            profile_text_color='#FFFFFF',
            avatar_text='U',
        ),
    )


def _definition() -> NavigationDefinition:
    return NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='guest',
                label='Guest',
                href='/guest',
                allowed_profiles=('guest',),
            ),
            NavigationLinkDefinition(
                key='admin-only',
                label='Admin only',
                href='/admin',
            ),
            NavigationLinkDefinition(
                key='disabled',
                label='Disabled',
                href='/disabled',
                enabled=False,
                allowed_profiles=('guest',),
            ),
        ),
        groups=(
            NavigationGroupDefinition(
                key='disabled-group',
                label='Disabled group',
                enabled=False,
                links=(
                    NavigationLinkDefinition(
                        key='disabled-child',
                        label='Disabled child',
                        href='/disabled-child',
                        allowed_profiles=('guest',),
                    ),
                ),
            ),
        ),
    )


def test_root_is_safe_for_every_ready_principal() -> None:
    definition = _definition()

    assert can_access_navigation_path(
        definition,
        principal=_principal('guest'),
        pathname='/',
    )


def test_restricted_principal_requires_explicit_route_permission() -> None:
    definition = _definition()

    assert can_access_navigation_path(
        definition,
        principal=_principal('guest'),
        pathname='/guest/',
    )
    assert not can_access_navigation_path(
        definition,
        principal=_principal('guest'),
        pathname='/admin',
    )
    assert not can_access_navigation_path(
        definition,
        principal=_principal('guest'),
        pathname='/not-configured',
    )


def test_unrestricted_principal_can_open_unconfigured_route_but_not_disabled_route() -> None:
    definition = _definition()
    principal = _principal('administrator', unrestricted=True)

    assert can_access_navigation_path(
        definition,
        principal=principal,
        pathname='/not-configured',
    )
    assert not can_access_navigation_path(
        definition,
        principal=principal,
        pathname='/disabled',
    )
    assert not can_access_navigation_path(
        definition,
        principal=principal,
        pathname='/disabled-child',
    )


def test_route_resolution_exposes_stable_key_for_future_tracking() -> None:
    match = resolve_navigation_route(_definition(), '/guest?from=test')

    assert match is not None
    assert match.key == 'guest'
    assert match.pathname == '/guest'
    assert match.allowed_profiles == ('guest',)


def test_duplicate_internal_path_is_rejected_by_authorization_policy() -> None:
    definition = NavigationDefinition(
        links=(
            NavigationLinkDefinition(key='one', label='One', href='/same'),
            NavigationLinkDefinition(key='two', label='Two', href='/same/'),
        )
    )

    with pytest.raises(WebDefinitionError, match='duplicated internal path'):
        resolve_navigation_route(definition, '/same')


def test_authorization_middleware_returns_access_denied_with_home_action() -> None:
    services = ServiceRegistry()
    navigation = create_navigation_module(
        _definition(),
        principal_provider=NavigationPrincipalProvider(lambda: _principal('guest')),
    )
    assert navigation.register_services is not None
    navigation.register_services(services)
    services.freeze()
    server = Flask(__name__)
    authorization = create_navigation_authorization_module()
    assert authorization.register_middlewares is not None
    authorization.register_middlewares(server, services)

    @server.get('/')
    def home():
        return 'home'

    @server.get('/guest')
    def guest():
        return 'guest'

    @server.get('/admin')
    def admin():
        return 'admin'

    client = server.test_client()

    assert client.get('/', headers={'Accept': 'text/html'}).status_code == 200
    assert client.get('/guest', headers={'Accept': 'text/html'}).status_code == 200
    denied = client.get('/admin', headers={'Accept': 'text/html'})
    assert denied.status_code == 403
    body = denied.get_data(as_text=True)
    assert 'Acceso denegado' in body
    assert 'No tienes acceso a esta página.' in body
    assert 'href="/"' in body
    assert 'Volver al inicio' in body


def test_platform_auth_route_bypasses_navigation_authorization() -> None:
    principal_calls = 0

    def current_principal() -> NavigationPrincipal:
        nonlocal principal_calls
        principal_calls += 1
        return _principal('guest')

    services = ServiceRegistry()
    navigation = create_navigation_module(
        _definition(),
        principal_provider=NavigationPrincipalProvider(current_principal),
    )
    assert navigation.register_services is not None
    navigation.register_services(services)
    services.freeze()
    server = Flask(__name__)
    authorization = create_navigation_authorization_module()
    assert authorization.register_middlewares is not None
    authorization.register_middlewares(server, services)

    @server.get('/.auth/logout')
    def logout():
        return 'logout'

    response = server.test_client().get('/.auth/logout', headers={'Accept': 'text/html'})

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'logout'
    assert principal_calls == 0
