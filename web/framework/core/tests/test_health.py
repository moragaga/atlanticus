from atlanticus.web.health import HealthRegistry


def test_health_registry_reports_check_failures_without_exposing_messages() -> None:
    health = HealthRegistry()
    health.add('ok', lambda: True)

    def fail() -> bool:
        raise RuntimeError('private detail')

    health.add('failed', fail)

    report = health.evaluate()

    assert report.ready is False
    assert report.as_dict() == {
        'status': 'not_ready',
        'checks': {
            'ok': {'status': 'healthy'},
            'failed': {'status': 'unhealthy', 'error_type': 'RuntimeError'},
        },
    }
