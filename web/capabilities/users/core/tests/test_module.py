from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.module import PROFILE_CATALOG_SERVICE_KEY, create_users_module
from atlanticus.web.users.profiles import ProfileCatalog
from atlanticus.web.users.runtime import USERS_RUNTIME_SERVICE_KEY, UsersRuntime


def test_users_module_registers_runtime_and_profile_catalog() -> None:
    runtime = UsersRuntime()
    profiles = ProfileCatalog()
    module = create_users_module(runtime, profiles)
    services = ServiceRegistry()

    assert module.register_services is not None
    module.register_services(services)

    assert services.require(USERS_RUNTIME_SERVICE_KEY, UsersRuntime) is runtime
    assert services.require(PROFILE_CATALOG_SERVICE_KEY, ProfileCatalog) is profiles
