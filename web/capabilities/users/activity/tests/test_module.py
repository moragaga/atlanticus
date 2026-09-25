from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.activity import MemoryUserActivityRepository, create_user_activity_module
from atlanticus.web.users.activity.routes import USER_ACTIVITY_SERVICE_KEY
from atlanticus.web.users.runtime import UsersRuntime


def test_module_publishes_assets_runtime_config_and_service() -> None:
    module = create_user_activity_module(
        repository=MemoryUserActivityRepository(),
        application_key='app',
        users_runtime=UsersRuntime(),
        heartbeat_seconds=30,
    )
    services = ServiceRegistry()
    module.register_services(services)

    assert module.name == 'user-activity'
    assert module.asset_layers[0].load_order == 30
    assert services.contains(USER_ACTIVITY_SERVICE_KEY)
    assert module.index.runtime_config == {
        'enabled': True,
        'bootstrap_endpoint': '/_atlanticus/activity/bootstrap',
        'event_endpoint': '/_atlanticus/activity/events',
        'heartbeat_ms': 30000,
    }
