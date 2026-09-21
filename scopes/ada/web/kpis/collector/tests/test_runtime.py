from __future__ import annotations

from threading import Event, get_ident

import pytest
from flask import Flask

from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_KPI_COLLECTOR_SERVICE_KEY,
    DEFAULT_KPI_LATEST_INTERVAL_SECONDS,
    DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS,
    AdaKpiCollectorPollingRuntime,
    KpiCollectorPollingSettings,
    KpiCollectorRefreshResult,
    KpiCollectorRefreshStatus,
    create_ada_kpi_collector_module,
)


class CollectorStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.thread_ids: list[int] = []
        self.refreshed = Event()
        self.latest_error: Exception | None = None
        self.timeseries_error: Exception | None = None

    def refresh_latest(self) -> KpiCollectorRefreshResult:
        self.calls.append('latest')
        self.thread_ids.append(get_ident())
        self.refreshed.set()
        if self.latest_error is not None:
            raise self.latest_error
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.UNCHANGED, 'latest-r1')

    def refresh_timeseries(self) -> KpiCollectorRefreshResult:
        self.calls.append('timeseries')
        self.thread_ids.append(get_ident())
        self.refreshed.set()
        if self.timeseries_error is not None:
            raise self.timeseries_error
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.UNCHANGED, 'timeseries-r1')


class ServiceRegistryStub:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, name: str, service: object) -> None:
        self.values[name] = service


def _module_server(collector: CollectorStub) -> tuple[Flask, ServiceRegistryStub]:
    module = create_ada_kpi_collector_module(
        collector,
        polling_settings=KpiCollectorPollingSettings(
            latest_interval_seconds=60,
            timeseries_interval_seconds=60,
        ),
    )
    services = ServiceRegistryStub()
    server = Flask(__name__)
    module.register_services(services)
    module.register_middlewares(server, services)

    @server.get('/')
    def home():
        return 'ok'

    @server.get('/health/live')
    def health():
        return {'status': 'ok'}

    @server.get('/assets/test.css')
    def asset():
        return 'asset'

    return server, services


def test_default_polling_intervals_are_latest_10_seconds_and_timeseries_120_seconds() -> None:
    settings = KpiCollectorPollingSettings()

    assert settings.latest_interval_seconds == DEFAULT_KPI_LATEST_INTERVAL_SECONDS == 10.0
    assert settings.timeseries_interval_seconds == DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS == 120.0


def test_polling_intervals_are_explicitly_configurable() -> None:
    settings = KpiCollectorPollingSettings(
        latest_interval_seconds=5,
        timeseries_interval_seconds=90,
    )

    assert settings.latest_interval_seconds == 5
    assert settings.timeseries_interval_seconds == 90


@pytest.mark.parametrize(
    ('field', 'value'),
    (
        ('latest_interval_seconds', 0),
        ('latest_interval_seconds', -1),
        ('timeseries_interval_seconds', 0),
        ('timeseries_interval_seconds', -1),
    ),
)
def test_polling_intervals_must_be_positive(field: str, value: float) -> None:
    values = {
        'latest_interval_seconds': 10,
        'timeseries_interval_seconds': 120,
        field: value,
    }

    with pytest.raises(ValueError, match=f'{field} must be greater than zero and finite'):
        KpiCollectorPollingSettings(**values)


def test_latest_and_timeseries_keep_independent_schedules_with_latest_priority() -> None:
    collector = CollectorStub()
    runtime = AdaKpiCollectorPollingRuntime(collector)

    for second in range(0, 121, 10):
        runtime.poll_due(now=float(second))

    assert collector.calls.count('latest') == 13
    assert collector.calls.count('timeseries') == 2
    assert collector.calls[:2] == ['latest', 'timeseries']
    assert collector.calls[-2:] == ['latest', 'timeseries']


def test_latest_failure_does_not_block_due_timeseries_refresh() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('latest failed')
    runtime = AdaKpiCollectorPollingRuntime(collector)

    cycle = runtime.poll_due(now=0.0)

    assert isinstance(cycle.latest_error, RuntimeError)
    assert cycle.timeseries is not None
    assert collector.calls == ['latest', 'timeseries']


def test_polling_runtime_recovers_after_transient_source_failure() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('container missing')
    runtime = AdaKpiCollectorPollingRuntime(
        collector,
        settings=KpiCollectorPollingSettings(
            latest_interval_seconds=10,
            timeseries_interval_seconds=120,
        ),
    )

    failed_cycle = runtime.poll_due(now=0.0)
    collector.latest_error = None
    recovered_cycle = runtime.poll_due(now=10.0)

    assert isinstance(failed_cycle.latest_error, RuntimeError)
    assert recovered_cycle.latest is not None
    assert recovered_cycle.latest_error is None


def test_web_module_registers_application_scoped_cache_and_poller() -> None:
    collector = CollectorStub()
    server, services = _module_server(collector)

    assert services.values[ADA_KPI_COLLECTOR_SERVICE_KEY] is collector
    polling_runtime = services.values[ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY]
    assert isinstance(polling_runtime, AdaKpiCollectorPollingRuntime)
    assert len(server.before_request_funcs[None]) == 1


def test_health_and_assets_never_start_collector() -> None:
    collector = CollectorStub()
    server, services = _module_server(collector)
    polling_runtime = services.values[ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY]
    client = server.test_client()

    assert client.get('/health/live').status_code == 200
    assert client.get('/assets/test.css').status_code == 200
    assert not polling_runtime.is_running
    assert collector.calls == []


def test_application_request_starts_background_poller_without_refreshing_inline() -> None:
    collector = CollectorStub()
    server, services = _module_server(collector)
    polling_runtime = services.values[ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY]
    request_thread_id = get_ident()

    assert server.test_client().get('/').status_code == 200
    assert collector.refreshed.wait(1.0)

    polling_runtime.stop()
    assert collector.thread_ids
    assert all(thread_id != request_thread_id for thread_id in collector.thread_ids)


def test_background_poller_survives_initial_source_failure_without_breaking_request() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('latest container unavailable')
    collector.timeseries_error = RuntimeError('timeseries container unavailable')
    server, services = _module_server(collector)
    polling_runtime = services.values[ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY]

    assert server.test_client().get('/').status_code == 200
    assert collector.refreshed.wait(1.0)
    assert polling_runtime.is_running

    polling_runtime.stop()
