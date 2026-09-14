from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.module import create_users_module
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime


def test_users_module_registers_runtime() -> None:
    runtime = UsersRuntime()
    module = create_users_module(runtime)
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)

    assert services.require(USERS_RUNTIME_SERVICE_KEY, UsersRuntime) is runtime
