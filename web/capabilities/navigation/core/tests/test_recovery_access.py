import pytest
from flask import Flask

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.navigation.api import (
    NavigationDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    can_access_navigation_path,
    create_navigation_authorization_module,
    create_navigation_module,
    resolve_navigation,
)
from atlanticus.web.services import ServiceRegistry


def _principal(
    profile: str | None,
    *,
    administrative_override: bool = False,
    unrestricted: bool = False,
) -> NavigationPrincipal:
    return NavigationPrincipal(
        access_key=profile,
        administrative_override=administrative_override,
        unrestricted=unrestricted,
        user=NavigationUser(
            display_name='Visitante' if profile is None else 'Administrator',
            profile_key=profile or 'guest',
            profile_label='Visual only' if profile is None else profile.title(),
            profile_background_color='#123456',
            profile_text_color='#FFFFFF',
            avatar_text='V' if profile is None else 'A',
        ),
    )


def _definition() -> NavigationDefinition:
    return NavigationDefinition(
        links=(
            NavigationLinkDefinition(key='home', label='Home', href='/'),
            NavigationLinkDefinition(key='public', label='Public', href='/public'),
            NavigationLinkDefinition(
                key='guest', label='Guest', href='/guest', allowed_profiles=('guest',)
            ),
            NavigationLinkDefinition(
                key='restricted',
                label='Restricted',
                href='/restricted',
                allowed_profiles=('operator',),
            ),
            NavigationLinkDefinition(key='disabled', label='Disabled', href='/disabled', enabled=False),
        ),
        home_route_key='home',
    )


def test_anonymous_visual_guest_does_not_grant_guest_permissions() -> None:
    principal = _principal(None)
    definition = _definition()
    menu = resolve_navigation(definition, principal=principal)

    assert tuple(link.key for link in menu.links) == ('home', 'public')
    assert can_access_navigation_path(definition, principal=principal, pathname='/')
    assert can_access_navigation_path(definition, principal=principal, pathname='/public')
    assert not can_access_navigation_path(definition, principal=principal, pathname='/guest')
    assert not can_access_navigation_path(definition, principal=principal, pathname='/restricted')
    assert not can_access_navigation_path(definition, principal=principal, pathname='/disabled')
    assert not can_access_navigation_path(definition, principal=principal, pathname='/manager')


@pytest.mark.parametrize('profile', ['root', 'local'])
def test_root_and_local_require_explicit_trusted_override(profile: str) -> None:
    definition = _definition()
    plain = _principal(profile, unrestricted=True)
    privileged = _principal(profile, administrative_override=True)

    assert not can_access_navigation_path(definition, principal=plain, pathname='/disabled')
    assert not can_access_navigation_path(definition, principal=plain, pathname='/manager')
    assert can_access_navigation_path(definition, principal=privileged, pathname='/disabled')
    assert can_access_navigation_path(definition, principal=privileged, pathname='/manager')
    assert can_access_navigation_path(definition, principal=privileged, pathname='/restricted')
    assert 'disabled' not in tuple(
        link.key for link in resolve_navigation(definition, principal=privileged).links
    )


def test_empty_navigation_keeps_only_home_public_during_bootstrap() -> None:
    empty = NavigationDefinition()
    anonymous = _principal(None)
    privileged = _principal('root', administrative_override=True)

    assert can_access_navigation_path(empty, principal=anonymous, pathname='/')
    assert not can_access_navigation_path(empty, principal=anonymous, pathname='/manager')
    assert can_access_navigation_path(empty, principal=privileged, pathname='/manager')


def test_explicitly_disabled_home_is_not_unconditionally_public() -> None:
    definition = NavigationDefinition(
        links=(NavigationLinkDefinition(key='home', label='Home', href='/', enabled=False),),
        home_route_key='home',
    )
    assert not can_access_navigation_path(definition, principal=_principal(None), pathname='/')
    assert can_access_navigation_path(
        definition, principal=_principal('local', administrative_override=True), pathname='/'
    )


def test_administrative_override_rejects_truthy_non_boolean() -> None:
    with pytest.raises(WebDefinitionError, match='administrative override must be boolean'):
        NavigationPrincipal(
            access_key='root',
            user=_principal('root').user,
            administrative_override='true',
        )


def test_navigation_http_without_identity_protects_unlisted_and_disabled_routes() -> None:
    current = [_principal(None)]
    services = ServiceRegistry()
    navigation = create_navigation_module(
        _definition(), principal_provider=NavigationPrincipalProvider(lambda: current[0])
    )
    navigation.register_services(services)
    services.freeze()
    server = Flask(__name__)
    authorization = create_navigation_authorization_module()
    authorization.register_middlewares(server, services)

    @server.get('/')
    def home():
        return 'home'

    @server.get('/public')
    def public():
        return 'public'

    @server.get('/guest')
    def guest():
        return 'guest'

    @server.get('/disabled')
    def disabled():
        return 'disabled'

    @server.get('/manager')
    def manager():
        return 'manager'

    client = server.test_client()
    headers = {'Accept': 'text/html'}
    assert client.get('/', headers=headers).status_code == 200
    assert client.get('/public', headers=headers).status_code == 200
    assert client.get('/guest', headers=headers).status_code == 403
    assert client.get('/disabled', headers=headers).status_code == 403
    assert client.get('/manager', headers=headers).status_code == 403

    current[0] = _principal('root', administrative_override=True)
    assert client.get('/disabled', headers=headers).status_code == 200
    assert client.get('/manager', headers=headers).status_code == 200
