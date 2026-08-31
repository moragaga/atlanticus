from atlanticus.web.compositions.navigation_activity import (
    NavigationActivityRouteResolver,
    create_navigation_activity_route_resolver,
    create_navigation_user_activity_module,
)
from atlanticus.web.navigation.models import (
    NavigationDefinition,
    NavigationGroupDefinition,
    NavigationLinkDefinition,
)


def _definition() -> NavigationDefinition:
    return NavigationDefinition(
        links=(
            NavigationLinkDefinition(key='home', label='Home', href='/'),
            NavigationLinkDefinition(key='external', label='External', href='https://example.com'),
        ),
        groups=(
            NavigationGroupDefinition(
                key='manager',
                label='Manager',
                links=(
                    NavigationLinkDefinition(key='users', label='Users', href='/manager/users/'),
                    NavigationLinkDefinition(
                        key='disabled', label='Disabled', href='/manager/disabled', enabled=False
                    ),
                ),
            ),
        ),
        home_route_key='home',
    )


def test_resolver_maps_only_enabled_internal_routes() -> None:
    resolver = NavigationActivityRouteResolver(_definition())

    assert resolver.resolve('/').key == 'home'
    assert resolver.resolve('/manager/users').key == 'users'
    assert resolver.resolve('/manager/users/').key == 'users'
    assert resolver.resolve('/manager/disabled') is None
    assert resolver.resolve('https://example.com') is None


def test_factory_returns_route_resolver() -> None:
    resolver = create_navigation_activity_route_resolver(_definition())

    assert isinstance(resolver, NavigationActivityRouteResolver)
    assert resolver.resolve('/missing') is None


def test_composition_factory_builds_activity_module() -> None:
    from atlanticus.web.users.activity import MemoryUserActivityRepository

    module = create_navigation_user_activity_module(
        _definition(),
        repository=MemoryUserActivityRepository(),
        application_key='app',
    )

    assert module.name == 'user-activity'
    assert module.index.runtime_config['heartbeat_ms'] == 30000
