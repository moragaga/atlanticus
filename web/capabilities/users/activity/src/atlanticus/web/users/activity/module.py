from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.activity.contracts import ActivityRouteResolver, UserActivityRepository
from atlanticus.web.users.activity.routes import (
    USER_ACTIVITY_BOOTSTRAP_PATH,
    USER_ACTIVITY_EVENT_PATH,
    USER_ACTIVITY_SERVICE_KEY,
    register_user_activity_routes,
)
from atlanticus.web.users.activity.services import UserActivityService

USER_ACTIVITY_ASSET_LAYER = AssetLayer(
    name='atlanticus_web_user_activity',
    load_order=30,
    package='atlanticus.web.users.activity',
)


def create_user_activity_module(
    *,
    repository: UserActivityRepository,
    application_key: str,
    route_resolver: ActivityRouteResolver | None = None,
    heartbeat_seconds: int = 30,
    track_local: bool = False,
) -> WebModule:
    if heartbeat_seconds < 5:
        raise ValueError('User activity heartbeat must be at least 5 seconds')

    def register_services(services: ServiceRegistry) -> None:
        services.add(
            USER_ACTIVITY_SERVICE_KEY,
            UserActivityService(
                repository=repository,
                application_key=application_key,
                route_resolver=route_resolver,
                track_local=track_local,
            ),
        )

    def register_routes(server, services: ServiceRegistry) -> None:
        register_user_activity_routes(server, services)

    return WebModule(
        name='user-activity',
        asset_layers=(USER_ACTIVITY_ASSET_LAYER,),
        register_services=register_services,
        register_routes=register_routes,
        index=IndexContribution(
            runtime_config={
                'enabled': True,
                'bootstrap_endpoint': USER_ACTIVITY_BOOTSTRAP_PATH,
                'event_endpoint': USER_ACTIVITY_EVENT_PATH,
                'heartbeat_ms': heartbeat_seconds * 1000,
            }
        ),
    )
