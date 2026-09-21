from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic
from typing import Protocol

from ada.web.kpis.collector.models import (
    KpiCollectorContractError,
    KpiCollectorRefreshResult,
    KpiDeliveryReadError,
)
from atlanticus.web.observability import WebObservability

DEFAULT_KPI_LATEST_INTERVAL_SECONDS = 10.0
DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS = 120.0


def _validate_interval(value: object, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f'{field_name} must be greater than zero and finite')


def _advance_missed_deadline(
    deadline: float | None,
    *,
    interval_seconds: float,
    completed_at: float,
) -> float | None:
    if deadline is None or deadline > completed_at:
        return deadline
    missed_intervals = math.floor((completed_at - deadline) / interval_seconds) + 1
    return deadline + missed_intervals * interval_seconds


class _Collector(Protocol):
    def refresh_latest(self) -> KpiCollectorRefreshResult: ...

    def refresh_timeseries(self) -> KpiCollectorRefreshResult: ...


@dataclass(frozen=True, slots=True)
class KpiCollectorPollingSettings:
    latest_interval_seconds: float = DEFAULT_KPI_LATEST_INTERVAL_SECONDS
    timeseries_interval_seconds: float = DEFAULT_KPI_TIMESERIES_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        _validate_interval(self.latest_interval_seconds, 'latest_interval_seconds')
        _validate_interval(self.timeseries_interval_seconds, 'timeseries_interval_seconds')


@dataclass(frozen=True, slots=True)
class KpiCollectorPollCycle:
    latest: KpiCollectorRefreshResult | None = None
    timeseries: KpiCollectorRefreshResult | None = None
    latest_error: Exception | None = None
    timeseries_error: Exception | None = None


class AdaKpiCollectorPollingRuntime:
    def __init__(
        self,
        collector: _Collector,
        *,
        observability: WebObservability,
        settings: KpiCollectorPollingSettings | None = None,
        clock: Callable[[], float] = monotonic,
        pid_provider: Callable[[], int] = os.getpid,
    ) -> None:
        if not callable(getattr(collector, 'refresh_latest', None)):
            raise TypeError('collector must provide a callable refresh_latest method')
        if not callable(getattr(collector, 'refresh_timeseries', None)):
            raise TypeError('collector must provide a callable refresh_timeseries method')
        if not isinstance(observability, WebObservability):
            raise TypeError('observability must be WebObservability')
        resolved_settings = settings or KpiCollectorPollingSettings()
        if not isinstance(resolved_settings, KpiCollectorPollingSettings):
            raise TypeError('settings must be KpiCollectorPollingSettings')
        if not callable(clock):
            raise TypeError('clock must be callable')
        if not callable(pid_provider):
            raise TypeError('pid_provider must be callable')
        self._collector = collector
        self._observability = observability
        self._settings = resolved_settings
        self._clock = clock
        self._pid_provider = pid_provider
        self._state_lock = Lock()
        self._poll_lock = Lock()
        self._stop_event: Event | None = None
        self._thread: Thread | None = None
        self._pid: int | None = None
        self._next_latest_due: float | None = None
        self._next_timeseries_due: float | None = None
        self._incident_signatures: dict[str, tuple[str, str]] = {}

    @property
    def settings(self) -> KpiCollectorPollingSettings:
        return self._settings

    @property
    def worker_pid(self) -> int | None:
        with self._state_lock:
            return self._pid

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._is_running_locked(self._pid_provider())

    def ensure_started(self) -> bool:
        pid = self._pid_provider()
        with self._state_lock:
            if self._is_running_locked(pid):
                return False
            stop_event = Event()
            self._stop_event = stop_event
            self._pid = pid
            self._next_latest_due = None
            self._next_timeseries_due = None
            thread = Thread(
                target=self._run,
                args=(pid, stop_event),
                name=f'ada-kpi-collector-{pid}',
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return True

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        _validate_interval(timeout_seconds, 'timeout_seconds')
        pid = self._pid_provider()
        with self._state_lock:
            if self._pid != pid:
                return
            stop_event = self._stop_event
            thread = self._thread
        if stop_event is None or thread is None:
            return
        stop_event.set()
        thread.join(timeout_seconds)
        if thread.is_alive():
            return
        with self._state_lock:
            if self._pid == pid and self._thread is thread:
                self._thread = None
                self._stop_event = None
                self._pid = None
                self._next_latest_due = None
                self._next_timeseries_due = None

    def poll_due(self, *, now: float | None = None) -> KpiCollectorPollCycle:
        current = self._clock() if now is None else now
        if (
            isinstance(current, bool)
            or not isinstance(current, int | float)
            or not math.isfinite(current)
        ):
            raise TypeError('now must be a finite numeric value')
        if not self._poll_lock.acquire(blocking=False):
            return KpiCollectorPollCycle()
        try:
            latest_due = self._next_latest_due is None or current >= self._next_latest_due
            timeseries_due = (
                self._next_timeseries_due is None or current >= self._next_timeseries_due
            )
            if latest_due:
                self._next_latest_due = current + self._settings.latest_interval_seconds
            if timeseries_due:
                self._next_timeseries_due = current + self._settings.timeseries_interval_seconds

            latest_result = None
            latest_error = None
            timeseries_result = None
            timeseries_error = None
            if latest_due:
                try:
                    latest_result = self._collector.refresh_latest()
                except Exception as error:
                    latest_error = error
                    self._report_refresh_failure('latest', error)
                else:
                    self._clear_refresh_failure('latest')
            if timeseries_due:
                try:
                    timeseries_result = self._collector.refresh_timeseries()
                except Exception as error:
                    timeseries_error = error
                    self._report_refresh_failure('timeseries', error)
                else:
                    self._clear_refresh_failure('timeseries')
            return KpiCollectorPollCycle(
                latest=latest_result,
                timeseries=timeseries_result,
                latest_error=latest_error,
                timeseries_error=timeseries_error,
            )
        finally:
            try:
                if now is None:
                    self._discard_missed_deadlines(self._clock())
            finally:
                self._poll_lock.release()

    def _run(self, pid: int, stop_event: Event) -> None:
        try:
            while not stop_event.is_set():
                if self._pid_provider() != pid:
                    return
                self.poll_due()
                stop_event.wait(self._seconds_until_next_poll())
        except Exception as error:
            self._observability.critical(
                'web.kpi_collector.runtime_failed',
                'KPI collector polling runtime failed',
                exception=error,
            )

    def _seconds_until_next_poll(self) -> float:
        with self._poll_lock:
            now = self._clock()
            deadlines = tuple(
                deadline
                for deadline in (self._next_latest_due, self._next_timeseries_due)
                if deadline is not None
            )
        if not deadlines:
            return 0.0
        return max(0.0, min(deadlines) - now)

    def _discard_missed_deadlines(self, completed_at: float) -> None:
        self._next_latest_due = _advance_missed_deadline(
            self._next_latest_due,
            interval_seconds=self._settings.latest_interval_seconds,
            completed_at=completed_at,
        )
        self._next_timeseries_due = _advance_missed_deadline(
            self._next_timeseries_due,
            interval_seconds=self._settings.timeseries_interval_seconds,
            completed_at=completed_at,
        )

    def _report_refresh_failure(self, source: str, error: Exception) -> None:
        signature = (type(error).__name__, str(error))
        if self._incident_signatures.get(source) == signature:
            return
        self._incident_signatures[source] = signature
        if isinstance(error, KpiDeliveryReadError):
            cause = error.__cause__
            self._observability.warning(
                'web.kpi_collector.delivery_unavailable',
                'KPI delivery source is unavailable',
                source=source,
                error_type=type(error).__name__,
                cause_type=(type(cause).__name__ if cause is not None else None),
            )
            return
        event_name = (
            'web.kpi_collector.contract_failed'
            if isinstance(error, KpiCollectorContractError)
            else 'web.kpi_collector.refresh_failed'
        )
        self._observability.error(
            event_name,
            'KPI collector refresh failed',
            exception=error,
            source=source,
        )

    def _clear_refresh_failure(self, source: str) -> None:
        self._incident_signatures.pop(source, None)

    def _is_running_locked(self, pid: int) -> bool:
        return self._pid == pid and self._thread is not None and self._thread.is_alive()
