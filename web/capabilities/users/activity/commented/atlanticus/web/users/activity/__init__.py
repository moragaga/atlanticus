# Superficie pública estable; evita acoplar consumidores a módulos internos.
from atlanticus.web.users.activity.adapters import (
    CosmosUserActivityRepository,
    MemoryUserActivityRepository,
)
from atlanticus.web.users.activity.contracts import ActivityRoute, ActivityRouteResolver
from atlanticus.web.users.activity.models import (
    Screen,
    UserActivityDocument,
    UserActivityEvent,
    UserActivityEventType,
    Viewport,
)
from atlanticus.web.users.activity.module import (
    USER_ACTIVITY_ASSET_LAYER,
    create_user_activity_module,
)
from atlanticus.web.users.activity.services import UserActivityService
from atlanticus.web.users.activity.storage import (
    USER_ACTIVITY_STORAGE_RESOURCE,
    USER_ACTIVITY_STORAGE_RESOURCES,
)

__all__ = [
    'ActivityRoute',
    'ActivityRouteResolver',
    'CosmosUserActivityRepository',
    'MemoryUserActivityRepository',
    'Screen',
    'USER_ACTIVITY_ASSET_LAYER',
    'USER_ACTIVITY_STORAGE_RESOURCE',
    'USER_ACTIVITY_STORAGE_RESOURCES',
    'UserActivityDocument',
    'UserActivityEvent',
    'UserActivityEventType',
    'UserActivityService',
    'Viewport',
    'create_user_activity_module',
]
