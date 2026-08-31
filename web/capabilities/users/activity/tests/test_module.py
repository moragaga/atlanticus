from pathlib import Path

from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.activity import MemoryUserActivityRepository, create_user_activity_module
from atlanticus.web.users.activity.routes import USER_ACTIVITY_SERVICE_KEY


def test_module_publishes_assets_runtime_config_and_service() -> None:
    module = create_user_activity_module(
        repository=MemoryUserActivityRepository(),
        application_key='app',
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


def test_javascript_uses_add_event_listener_and_no_click_tracking() -> None:
    asset = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/users/activity/resources/js/10_user_activity.js'
    ).read_text(encoding='utf-8')

    assert "runtime?.modules?.['user-activity']" in asset
    assert "document.addEventListener('visibilitychange'" in asset
    assert "window.addEventListener('pagehide'" in asset
    assert 'window.history[method]' in asset
    assert 'sessionStorage' in asset
    assert "addEventListener('click'" not in asset
    assert 'appInsights' not in asset
    assert 'ada-' not in asset.lower()
