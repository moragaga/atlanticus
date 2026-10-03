from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)


def _catalog() -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='dashboard',
                label='Dashboard',
                href='/',
                icon='bi bi-house',
                access_mode='restricted',
                allowed_profiles=('guest', 'operator'),
            ),
            NavigationLinkConfiguration(
                key='logout',
                label='Logout',
                href='/.auth/logout',
                access_mode='public',
                force_reload=True,
            ),
        ),
        groups=(
            NavigationGroupConfiguration(
                key='configuration',
                label='Configuration',
                links=(
                    NavigationLinkConfiguration(
                        key='tools',
                        label='Tools',
                        href='/tools',
                        access_mode='restricted',
                        allowed_profiles=('operator',),
                    ),
                    NavigationLinkConfiguration(
                        key='public',
                        label='Public',
                        href='/public',
                        access_mode='restricted',
                        allowed_profiles=('guest',),
                    ),
                ),
            ),
        ),
    )


def test_configuration_round_trip_preserves_navigation_contract() -> None:
    catalog = _catalog()

    restored = NavigationConfigurationCatalog.from_document(catalog.to_document())
    definition = restored.to_definition()

    assert restored == catalog
    assert definition.home_route_key is None
    assert definition.find_link('dashboard').href == '/'
    assert definition.find_link('logout').force_reload is True
    assert definition.groups[0].expanded is False
    assert definition.groups[0].links[0].allowed_profiles == ('operator',)


def test_configuration_allows_empty_sections() -> None:
    catalog = NavigationConfigurationCatalog(
        groups=(NavigationGroupConfiguration(key='operations', label='Operations'),)
    )

    definition = catalog.to_definition()

    assert definition.groups[0].key == 'operations'
    assert definition.groups[0].links == ()


def test_configuration_accepts_manual_profile_keys_without_users() -> None:
    catalog = NavigationConfigurationCatalog(
        links=(
            NavigationLinkConfiguration(
                key='dashboard',
                label='Dashboard',
                href='/',
                access_mode='restricted',
                allowed_profiles=('manual_operator', 'guest'),
            ),
        ),
    )

    assert catalog.configured_profiles() == ('manual_operator', 'guest')


def test_configuration_requires_explicit_access_mode_in_documents() -> None:
    import pytest

    from atlanticus.web.navigation.configuration.errors import (
        NavigationConfigurationValidationError,
    )

    with pytest.raises(NavigationConfigurationValidationError):
        NavigationConfigurationCatalog.from_document(
            {
                'links': [
                    {
                        'key': 'home',
                        'label': 'Home',
                        'href': '/',
                        'allowed_profiles': [],
                    }
                ],
                'groups': [],
            }
        )


def test_restricted_configuration_accepts_zero_ordinary_profiles() -> None:
    link = NavigationLinkConfiguration(
        key='private',
        label='Private',
        href='/private',
        access_mode='restricted',
    )

    assert link.allowed_profiles == ()
    assert link.to_document()['access_mode'] == 'restricted'
