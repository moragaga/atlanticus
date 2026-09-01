from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.profiles import ProfileCatalog
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime

PROFILE_CATALOG_SERVICE_KEY = 'atlanticus.web.users.profiles'


def create_users_module(runtime: UsersRuntime, profiles: ProfileCatalog) -> WebModule:
    def register_services(services: ServiceRegistry) -> None:
        services.add(USERS_RUNTIME_SERVICE_KEY, runtime)
        services.add(PROFILE_CATALOG_SERVICE_KEY, profiles)

    return WebModule(
        name='users',
        register_services=register_services,
    )
