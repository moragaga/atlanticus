from pathlib import Path

import pytest

from atlanticus.web.errors import ServiceRegistryError, WebDefinitionError
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationDefinition,
    NavigationDefinitionProvider,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
    create_navigation_module,
    resolve_navigation,
    resolve_navigation_from_services,
)
from atlanticus.web.services import ServiceRegistry


def _user(profile_key: str = 'viewer') -> NavigationUser:
    return NavigationUser(
        display_name='John Doe',
        email='john@example.com',
        profile_key=profile_key,
        profile_label=profile_key.title(),
        profile_background_color='#123456',
        profile_text_color='#FFFFFF',
        avatar_text='JD',
    )


def _principal(profile_key: str, *, unrestricted: bool = False) -> NavigationPrincipal:
    return NavigationPrincipal(
        access_key=profile_key,
        unrestricted=unrestricted,
        user=_user(profile_key),
    )


def _definition() -> NavigationDefinition:
    return NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='private',
                label='Privado',
                href='/private',
            ),
            NavigationLinkDefinition(
                key='viewer-home',
                label='Viewer',
                href='/viewer',
                allowed_profiles=('viewer',),
            ),
        ),
        groups=(
            NavigationGroupDefinition(
                key='main',
                label='Main',
                allowed_profiles=('viewer',),
                links=(
                    NavigationLinkDefinition(
                        key='inherited',
                        label='Inherited',
                        href='/inherited',
                    ),
                    NavigationLinkDefinition(
                        key='override',
                        label='Override',
                        href='/override',
                        allowed_profiles=('analyst',),
                    ),
                ),
            ),
        ),
    )


def test_unrestricted_principal_receives_all_navigation_without_profile_assignment() -> None:
    menu = resolve_navigation(
        _definition(),
        principal=_principal('manual-admin', unrestricted=True),
    )

    assert tuple(link.key for link in menu.links) == ('private', 'viewer-home')
    assert tuple(link.key for link in menu.groups[0].links) == ('inherited', 'override')


def test_restricted_principal_filters_links_and_child_can_override_group_profiles() -> None:
    viewer = resolve_navigation(_definition(), principal=_principal('viewer'))
    analyst = resolve_navigation(_definition(), principal=_principal('analyst'))

    assert tuple(link.key for link in viewer.links) == ('viewer-home',)
    assert tuple(link.key for link in viewer.groups[0].links) == ('inherited',)
    assert analyst.links == ()
    assert tuple(link.key for link in analyst.groups[0].links) == ('override',)


def test_guest_is_just_a_manual_profile_key_for_navigation_core() -> None:
    definition = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='guest-home',
                label='Guest',
                href='/guest',
                allowed_profiles=('guest',),
            ),
        )
    )

    menu = resolve_navigation(definition, principal=_principal('guest'))

    assert tuple(link.key for link in menu.links) == ('guest-home',)


def test_navigation_core_does_not_reserve_users_profile_keys() -> None:
    definition = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='manual-administrator',
                label='Administrator',
                href='/administrator',
                allowed_profiles=('administrator',),
            ),
        )
    )

    menu = resolve_navigation(definition, principal=_principal('administrator'))

    assert tuple(link.key for link in menu.links) == ('manual-administrator',)


def test_navigation_definition_exposes_configured_profile_keys_without_catalog() -> None:
    assert _definition().configured_profiles() == ('viewer', 'analyst')


def test_navigation_user_normalizes_visual_contract() -> None:
    user = NavigationUser(
        display_name=' John Doe ',
        email='john@example.com',
        profile_key=' Viewer ',
        profile_label=' Visualizador ',
        profile_background_color='#123456',
        profile_text_color='#abcdef',
        avatar_text=' JD ',
        avatar_background_color='#654321',
        avatar_text_color='#fedcba',
    )

    assert user.display_name == 'John Doe'
    assert user.profile_key == 'viewer'
    assert user.profile_label == 'Visualizador'
    assert user.profile_text_color == '#ABCDEF'
    assert user.avatar_background_color == '#654321'
    assert user.avatar_text_color == '#FEDCBA'


def test_navigation_definition_allows_empty_group_without_rendering_it() -> None:
    definition = NavigationDefinition(
        groups=(
            NavigationGroupDefinition(
                key='empty',
                label='Empty',
                links=(),
            ),
        ),
    )
    menu = resolve_navigation(
        definition,
        principal=_principal('guest'),
    )

    assert definition.groups[0].links == ()
    assert menu.groups == ()


def test_navigation_definition_can_reference_internal_home_route() -> None:
    definition = NavigationDefinition(
        links=(NavigationLinkDefinition(key='home', label='Home', href='/'),),
        home_route_key='home',
    )

    assert definition.home_route_key == 'home'
    assert definition.find_link('home').href == '/'


def test_navigation_definition_rejects_missing_or_external_home_route() -> None:
    with pytest.raises(WebDefinitionError, match='must reference a link'):
        NavigationDefinition(
            links=(NavigationLinkDefinition(key='home', label='Home', href='/'),),
            home_route_key='missing',
        )

    with pytest.raises(WebDefinitionError, match='internal link'):
        NavigationDefinition(
            links=(
                NavigationLinkDefinition(
                    key='external',
                    label='External',
                    href='https://example.com',
                ),
            ),
            home_route_key='external',
        )


def test_navigation_module_registers_definition_without_principal_provider() -> None:
    definition = _definition()
    module = create_navigation_module(definition)
    services = ServiceRegistry()

    assert module.name == 'navigation'
    assert module.register_services is not None
    module.register_services(services)
    provider = services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )
    assert provider.current() is definition
    assert not services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)


def test_navigation_resolves_from_manual_provider_without_users() -> None:
    definition = _definition()
    provider = NavigationPrincipalProvider(lambda: _principal('viewer'))
    module = create_navigation_module(definition, principal_provider=provider)
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)
    menu = resolve_navigation_from_services(services)

    assert tuple(link.key for link in menu.links) == ('viewer-home',)
    assert tuple(link.key for link in menu.groups[0].links) == ('inherited',)


def test_service_resolution_requires_principal_provider_only_when_menu_is_requested() -> None:
    module = create_navigation_module(_definition())
    services = ServiceRegistry()
    assert module.register_services is not None
    module.register_services(services)

    with pytest.raises(ServiceRegistryError, match='principal-provider'):
        resolve_navigation_from_services(services)


def test_invalid_profile_key_is_rejected_without_external_catalog() -> None:
    with pytest.raises(WebDefinitionError, match='must not contain spaces'):
        NavigationLinkDefinition(
            key='invalid-profile',
            label='Invalid',
            href='/invalid',
            allowed_profiles=('not valid',),
        )


def test_navigation_package_has_no_users_dependency_or_import() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources


def test_navigation_root_remains_a_namespace_for_optional_extensions() -> None:
    root = Path(__file__).parents[1] / 'src' / 'atlanticus' / 'web' / 'navigation'

    assert not (root / '__init__.py').exists()
    assert (root / 'api.py').is_file()


def test_resolver_omits_disabled_links_and_groups() -> None:
    definition = NavigationDefinition(
        links=(
            NavigationLinkDefinition(
                key='hidden',
                label='Hidden',
                href='/hidden',
                enabled=False,
                allowed_profiles=('guest',),
            ),
        ),
        groups=(
            NavigationGroupDefinition(
                key='disabled-group',
                label='Disabled group',
                enabled=False,
                allowed_profiles=('guest',),
                links=(
                    NavigationLinkDefinition(
                        key='child',
                        label='Child',
                        href='/child',
                    ),
                ),
            ),
        ),
    )
    principal = NavigationPrincipal(
        access_key='guest',
        user=NavigationUser(
            display_name='Guest',
            profile_key='guest',
            profile_label='Guest',
            profile_background_color='#000000',
            profile_text_color='#FFFFFF',
            avatar_text='G',
        ),
    )

    menu = resolve_navigation(definition, principal=principal)

    assert menu.links == ()
    assert menu.groups == ()
