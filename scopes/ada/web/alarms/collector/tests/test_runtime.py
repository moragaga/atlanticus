from types import SimpleNamespace

from ada.web.alarms.collector.runtime import (
    AdaAlarmCollectorPollingRuntime,
    AlarmCollectorPollingSettings,
    DEFAULT_ALARM_POLL_INTERVAL_SECONDS,
)
from atlanticus.web.observability import WebObservability


class Collector:
    def __init__(self):
        self.calls = 0

    def refresh(self):
        self.calls += 1


def test_polling_does_not_scale_with_browser_refresh() -> None:
    collector = Collector()
    runtime = AdaAlarmCollectorPollingRuntime(
        collector,
        observability=object.__new__(WebObservability),
        settings=AlarmCollectorPollingSettings(interval_seconds=15),
        clock=lambda: 0.0,
    )
    assert runtime.poll_due(now=0).refreshed
    assert not runtime.poll_due(now=10).refreshed
    assert runtime.poll_due(now=15).refreshed
    assert collector.calls == 2


def test_default_polling_interval_is_five_seconds_and_configurable() -> None:
    assert DEFAULT_ALARM_POLL_INTERVAL_SECONDS == 5.0
    assert AlarmCollectorPollingSettings().interval_seconds == 5.0
    assert AlarmCollectorPollingSettings(interval_seconds=6).interval_seconds == 6

    collector = Collector()
    runtime = AdaAlarmCollectorPollingRuntime(
        collector, observability=object.__new__(WebObservability),
        clock=lambda: 0.0,
    )
    assert runtime.poll_due(now=0).refreshed
    assert not runtime.poll_due(now=4.9).refreshed
    assert runtime.poll_due(now=5).refreshed
    assert collector.calls == 2


class RecordingObservability(WebObservability):
    def __init__(self) -> None:
        self.warnings = []

    def warning(self, name, message, **kwargs):
        self.warnings.append((name, message, kwargs))


class RecoveringCollector:
    def __init__(self) -> None:
        self.calls = 0
        self.unavailable = True

    def refresh(self):
        self.calls += 1
        if self.unavailable:
            from ada.web.alarms.collector.models import AlarmLiveReadError
            raise AlarmLiveReadError('Could not read Alarm Live from Cosmos')


def test_unavailable_source_does_not_stop_polling_and_recovers() -> None:
    collector = RecoveringCollector()
    observability = RecordingObservability()
    runtime = AdaAlarmCollectorPollingRuntime(collector, observability=observability)

    first = runtime.poll_due(now=0)
    assert first.refreshed and first.error is not None
    second = runtime.poll_due(now=5)
    assert second.refreshed and second.error is not None
    assert len(observability.warnings) == 1

    collector.unavailable = False
    recovered = runtime.poll_due(now=10)
    assert recovered.refreshed and recovered.error is None
    assert collector.calls == 3

    collector.unavailable = True
    failed_again = runtime.poll_due(now=15)
    assert failed_again.refreshed and failed_again.error is not None
    assert len(observability.warnings) == 2


def test_polling_runtime_is_started_once_per_process(monkeypatch) -> None:
    from ada.web.alarms.collector import runtime as runtime_module

    created = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            self.name = name
            self.running = False
            created.append(self)

        def start(self):
            self.running = True

        def is_alive(self):
            return self.running

    monkeypatch.setattr(runtime_module, 'Thread', FakeThread)
    pid = [100]
    runtime = AdaAlarmCollectorPollingRuntime(
        Collector(),
        observability=object.__new__(WebObservability),
        pid_provider=lambda: pid[0],
    )

    assert runtime.ensure_started()
    assert not runtime.ensure_started()
    assert len(created) == 1
    assert runtime.worker_pid == 100

    pid[0] = 101
    assert runtime.ensure_started()
    assert not runtime.ensure_started()
    assert len(created) == 2
    assert runtime.worker_pid == 101
    assert [thread.name for thread in created] == [
        'ada-alarm-collector-100', 'ada-alarm-collector-101'
    ]
