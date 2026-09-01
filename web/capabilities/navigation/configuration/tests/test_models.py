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
                allowed_profiles=('guest', 'operator'),
            ),
            NavigationLinkConfiguration(
                key='logout',
                label='Logout',
                href='/.auth/logout',
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
                        allowed_profiles=('operator',),
                    ),
                    NavigationLinkConfiguration(
                        key='public',
                        label='Public',
                        href='/public',
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
    assert definition.groups[0].allowed_profiles == ()
    assert definition.groups[0].links[0].effective_profiles(definition.groups[0]) == ('operator',)


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
                allowed_profiles=('manual_operator', 'guest'),
            ),
        ),
    )

    assert catalog.configured_profiles() == ('manual_operator', 'guest')
