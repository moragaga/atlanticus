# Adapta Navigation al contrato pequeño de resolución de rutas de Activity.
# Sólo rutas internas, habilitadas y exactas reciben una route_key canónica.
from __future__ import annotations

from atlanticus.web.navigation.models import NavigationDefinition
from atlanticus.web.users.activity.contracts import ActivityRoute, UserActivityRepository
from atlanticus.web.users.activity.models import normalize_pathname
from atlanticus.web.users.activity.module import create_user_activity_module


class NavigationActivityRouteResolver:
    def __init__(self, definition: NavigationDefinition) -> None:
        routes: dict[str, ActivityRoute] = {}
        for link in definition.links:
            _add_route(routes, link.key, link.href, link.enabled, link.is_external)
        for group in definition.groups:
            if not group.enabled:
                continue
            for link in group.links:
                _add_route(routes, link.key, link.href, link.enabled, link.is_external)
        self._routes = routes

    def resolve(self, pathname: str) -> ActivityRoute | None:
        if not pathname.strip().startswith('/'):
            return None
        return self._routes.get(normalize_pathname(pathname))


def create_navigation_activity_route_resolver(
    definition: NavigationDefinition,
) -> NavigationActivityRouteResolver:
    return NavigationActivityRouteResolver(definition)


def create_navigation_user_activity_module(
    definition: NavigationDefinition,
    *,
    repository: UserActivityRepository,
    application_key: str,
    heartbeat_seconds: int = 30,
    track_local: bool = False,
):
    return create_user_activity_module(
        repository=repository,
        application_key=application_key,
        route_resolver=create_navigation_activity_route_resolver(definition),
        heartbeat_seconds=heartbeat_seconds,
        track_local=track_local,
    )


def _add_route(
    routes: dict[str, ActivityRoute],
    key: str,
    href: str,
    enabled: bool,
    external: bool,
) -> None:
    if not enabled or external:
        return
    pathname = normalize_pathname(href)
    routes[pathname] = ActivityRoute(key=key, pathname=pathname)
