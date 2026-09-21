from __future__ import annotations

import logging
import os
from threading import Event, Thread, get_ident
from time import monotonic

import pytest
from flask import Flask

from ada.web.kpis.collector import (
    ADA_KPI_COLLECTOR_RUNTIME_SERVICE_KEY,
    ADA_KPI_COLLECTOR_SERVICE_KEY,
    DEFAULT_KPI_LATEST_INTERVAL_SECONDS,
    DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS,
    AdaKpiCollectorPollingRuntime,
    KpiCollectorContractError,
    KpiCollectorPollCycle,
    KpiCollectorPollingSettings,
    KpiCollectorRefreshResult,
    KpiCollectorRefreshStatus,
    KpiDeliveryReadError,
    create_ada_kpi_collector_module,
)
from atlanticus.web.observability import WEB_OBSERVABILITY_SERVICE_KEY, WebObservability


class CollectorStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.thread_ids: list[int] = []
        self.refreshed = Event()
        self.latest_error: Exception | None = None
        self.timeseries_error: Exception | None = None
        self.latest_hook = None

    def refresh_latest(self) -> KpiCollectorRefreshResult:
        self.calls.append('latest')
        self.thread_ids.append(get_ident())
        self.refreshed.set()
        if self.latest_hook is not None:
            self.latest_hook()
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


class BlockingCollectorStub(CollectorStub):
    def __init__(self) -> None:
        super().__init__()
        self.latest_started = Event()
        self.latest_release = Event()

    def refresh_latest(self) -> KpiCollectorRefreshResult:
        self.calls.append('latest')
        self.thread_ids.append(get_ident())
        self.refreshed.set()
        self.latest_started.set()
        self.latest_release.wait(2.0)
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.UNCHANGED, 'latest-r1')


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RecordingWebObservability(WebObservability):
    def __init__(self) -> None:
        logger = logging.getLogger(f'test.kpi.collector.{id(self)}')
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        self.warning_events: list[tuple[str, str, dict[str, object]]] = []
        self.error_events: list[tuple[str, str, BaseException | None, dict[str, object]]] = []
        self.critical_events: list[tuple[str, str, BaseException | None, dict[str, object]]] = []
        self.critical_observed = Event()
        super().__init__(application='test', logger=logger, json_output=False)

    def warning(self, name: str, message: str, **context: object) -> None:
        self.warning_events.append((name, message, context))

    def error(
        self,
        name: str,
        message: str,
        *,
        exception: BaseException | None = None,
        **context: object,
    ) -> None:
        self.error_events.append((name, message, exception, context))

    def critical(
        self,
        name: str,
        message: str,
        *,
        exception: BaseException | None = None,
        **context: object,
    ) -> None:
        self.critical_events.append((name, message, exception, context))
        self.critical_observed.set()


class ServiceRegistryStub:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, name: str, service: object) -> None:
        self.values[name] = service

    def require(self, name: str, expected_type: type | None = None) -> object:
        value = self.values[name]
        if expected_type is not None and not isinstance(value, expected_type):
            raise TypeError
        return value


def _runtime(
    collector: CollectorStub,
    *,
    observability: RecordingWebObservability | None = None,
    settings: KpiCollectorPollingSettings | None = None,
    clock=monotonic,
    pid_provider=os.getpid,
) -> tuple[AdaKpiCollectorPollingRuntime, RecordingWebObservability]:
    resolved_observability = observability or RecordingWebObservability()
    return (
        AdaKpiCollectorPollingRuntime(
            collector,
            observability=resolved_observability,
            settings=settings,
            clock=clock,
            pid_provider=pid_provider,
        ),
        resolved_observability,
    )


def _module_server(collector: CollectorStub) -> tuple[Flask, ServiceRegistryStub]:
    module = create_ada_kpi_collector_module(
        collector,
        polling_settings=KpiCollectorPollingSettings(
            latest_interval_seconds=60,
            timeseries_interval_seconds=60,
        ),
    )
    services = ServiceRegistryStub()
    services.add(WEB_OBSERVABILITY_SERVICE_KEY, RecordingWebObservability())
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
    runtime, _ = _runtime(collector)

    for second in range(0, 121, 10):
        runtime.poll_due(now=float(second))

    assert collector.calls.count('latest') == 13
    assert collector.calls.count('timeseries') == 2
    assert collector.calls[:2] == ['latest', 'timeseries']
    assert collector.calls[-2:] == ['latest', 'timeseries']


def test_concurrent_poll_is_dropped_without_waiting_for_active_cycle() -> None:
    collector = BlockingCollectorStub()
    runtime, _ = _runtime(collector)
    first_poll = Thread(target=runtime.poll_due)
    first_poll.start()

    assert collector.latest_started.wait(1.0)

    second_result: list[KpiCollectorPollCycle] = []
    second_completed = Event()

    def run_second_poll() -> None:
        second_result.append(runtime.poll_due())
        second_completed.set()

    second_poll = Thread(target=run_second_poll)
    second_poll.start()

    assert second_completed.wait(1.0)
    assert second_result == [KpiCollectorPollCycle()]
    assert collector.calls == ['latest']

    collector.latest_release.set()
    first_poll.join(1.0)
    second_poll.join(1.0)

    assert not first_poll.is_alive()
    assert not second_poll.is_alive()
    assert collector.calls == ['latest', 'timeseries']


def test_slow_refresh_drops_missed_latest_slot_without_immediate_catch_up() -> None:
    clock = FakeClock()
    collector = CollectorStub()
    collector.latest_hook = lambda: clock.advance(12.0)
    runtime, _ = _runtime(collector, clock=clock)

    runtime.poll_due()

    assert clock() == 12.0
    assert collector.calls == ['latest', 'timeseries']

    runtime.poll_due()

    assert collector.calls == ['latest', 'timeseries']

    clock.advance(8.0)
    runtime.poll_due()

    assert collector.calls == ['latest', 'timeseries', 'latest']


def test_source_due_while_other_refresh_is_running_is_dropped_until_next_source_slot() -> None:
    clock = FakeClock()
    collector = CollectorStub()
    runtime, _ = _runtime(collector, clock=clock)

    runtime.poll_due(now=0.0)
    for second in range(10, 110, 10):
        runtime.poll_due(now=float(second))

    clock.value = 110.0
    collector.latest_hook = lambda: clock.advance(15.0)
    runtime.poll_due()

    assert clock() == 125.0
    assert collector.calls.count('timeseries') == 1

    collector.latest_hook = None
    clock.value = 130.0
    runtime.poll_due()

    assert collector.calls.count('latest') == 13
    assert collector.calls.count('timeseries') == 1

    clock.value = 240.0
    runtime.poll_due()

    assert collector.calls[-2:] == ['latest', 'timeseries']
    assert collector.calls.count('timeseries') == 2


def test_latest_failure_does_not_block_due_timeseries_refresh() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('latest failed')
    runtime, _ = _runtime(collector)

    cycle = runtime.poll_due(now=0.0)

    assert isinstance(cycle.latest_error, RuntimeError)
    assert cycle.timeseries is not None
    assert collector.calls == ['latest', 'timeseries']


def test_polling_runtime_recovers_after_transient_source_failure() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('container missing')
    runtime, _ = _runtime(
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


def test_delivery_read_failure_emits_one_warning_until_recovery() -> None:
    collector = CollectorStub()
    collector.latest_error = KpiDeliveryReadError('Could not read KPI delivery from Cosmos')
    runtime, observability = _runtime(collector)

    runtime.poll_due(now=0.0)
    runtime.poll_due(now=10.0)

    assert len(observability.warning_events) == 1
    name, _, context = observability.warning_events[0]
    assert name == 'web.kpi_collector.delivery_unavailable'
    assert context['source'] == 'latest'
    assert observability.error_events == []


def test_recovered_delivery_failure_can_be_reported_again() -> None:
    collector = CollectorStub()
    collector.latest_error = KpiDeliveryReadError('Could not read KPI delivery from Cosmos')
    runtime, observability = _runtime(collector)

    runtime.poll_due(now=0.0)
    collector.latest_error = None
    runtime.poll_due(now=10.0)
    collector.latest_error = KpiDeliveryReadError('Could not read KPI delivery from Cosmos')
    runtime.poll_due(now=20.0)

    assert len(observability.warning_events) == 2


def test_contract_failure_emits_deduplicated_error() -> None:
    collector = CollectorStub()
    collector.latest_error = KpiCollectorContractError('Latest contract is invalid')
    runtime, observability = _runtime(collector)

    runtime.poll_due(now=0.0)
    runtime.poll_due(now=10.0)

    assert len(observability.error_events) == 1
    name, _, exception, context = observability.error_events[0]
    assert name == 'web.kpi_collector.contract_failed'
    assert isinstance(exception, KpiCollectorContractError)
    assert context['source'] == 'latest'


def test_unexpected_refresh_failure_emits_deduplicated_error() -> None:
    collector = CollectorStub()
    collector.latest_error = RuntimeError('unexpected')
    runtime, observability = _runtime(collector)

    runtime.poll_due(now=0.0)
    runtime.poll_due(now=10.0)

    assert len(observability.error_events) == 1
    assert observability.error_events[0][0] == 'web.kpi_collector.refresh_failed'


def test_poll_lock_is_released_when_completion_clock_fails() -> None:
    collector = CollectorStub()
    clock_calls = 0

    def failing_completion_clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 2:
            raise RuntimeError('completion clock failed')
        return 0.0

    runtime, _ = _runtime(collector, clock=failing_completion_clock)

    with pytest.raises(RuntimeError, match='completion clock failed'):
        runtime.poll_due()

    recovered_cycle = runtime.poll_due(now=10.0)

    assert recovered_cycle.latest is not None


def test_unexpected_runtime_failure_emits_critical_event() -> None:
    collector = CollectorStub()
    observability = RecordingWebObservability()
    clock_calls = 0

    def failing_clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls > 1:
            raise RuntimeError('clock failed')
        return 0.0

    runtime, _ = _runtime(collector, observability=observability, clock=failing_clock)

    runtime.ensure_started()

    assert observability.critical_observed.wait(1.0)
    runtime.stop()
    assert len(observability.critical_events) == 1
    assert observability.critical_events[0][0] == 'web.kpi_collector.runtime_failed'


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
