# El módulo Users registra únicamente servicios que pertenecen a la capability Users.
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime


def create_users_module(runtime: UsersRuntime) -> WebModule:
    # El catálogo de Profiles se consume donde corresponde, por ejemplo en el resolver,
    # pero no se publica desde Users como si fuera un servicio propio.
    def register_services(services: ServiceRegistry) -> None:
        services.add(USERS_RUNTIME_SERVICE_KEY, runtime)

    return WebModule(
        name='users',
        register_services=register_services,
    )
