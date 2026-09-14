from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime


def create_users_module(runtime: UsersRuntime) -> WebModule:
    def register_services(services: ServiceRegistry) -> None:
        services.add(USERS_RUNTIME_SERVICE_KEY, runtime)

    return WebModule(name='users', register_services=register_services)
