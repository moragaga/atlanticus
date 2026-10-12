# Un hilo de polling por proceso Web; su frecuencia no depende de usuarios conectados.
from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic
from typing import Protocol

from ada.web.alarms.collector.contracts import AlarmLiveContractError
from ada.web.alarms.collector.models import AlarmLiveReadError
from atlanticus.web.observability import WebObservability

DEFAULT_ALARM_POLL_INTERVAL_SECONDS = 5.0


# Agrupa una responsabilidad operativa y sus invariantes.
class _Collector(Protocol):
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def refresh(self) -> object: ...


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorPollingSettings:
    interval_seconds: float = DEFAULT_ALARM_POLL_INTERVAL_SECONDS

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def __post_init__(self) -> None:
        if (
            isinstance(self.interval_seconds, bool)
            or not isinstance(self.interval_seconds, int | float)
            or not math.isfinite(self.interval_seconds)
            or self.interval_seconds <= 0
        ):
            raise ValueError('Alarm collector polling interval must be positive and finite')


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorPollCycle:
    refreshed: bool
    error: Exception | None = None


# Agrupa una responsabilidad operativa y sus invariantes.
class AdaAlarmCollectorPollingRuntime:
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def __init__(
        self, collector: _Collector, *, observability: WebObservability,
        settings: AlarmCollectorPollingSettings | None = None,
        clock: Callable[[], float] = monotonic,
        pid_provider: Callable[[], int] = os.getpid,
    ) -> None:
        if not callable(getattr(collector, 'refresh', None)):
            raise TypeError('Alarm collector must provide refresh')
        if not isinstance(observability, WebObservability):
            raise TypeError('Alarm collector requires WebObservability')
        self._collector = collector
        self._observability = observability
        self._settings = settings or AlarmCollectorPollingSettings()
        if not isinstance(self._settings, AlarmCollectorPollingSettings):
            raise TypeError('Alarm collector polling settings are invalid')
        if not callable(clock) or not callable(pid_provider):
            raise TypeError('Alarm collector clocks must be callable')
        self._clock = clock
        self._pid_provider = pid_provider
        self._lock = Lock()
        self._poll_lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None
        self._pid: int | None = None
        self._next_due: float | None = None
        self._last_incident: str | None = None

    @property
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def worker_pid(self) -> int | None:
        with self._lock:
            return self._pid

    @property
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def is_running(self) -> bool:
        with self._lock:
            return (
                self._pid == self._pid_provider()
                and self._thread is not None
                and self._thread.is_alive()
            )

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def ensure_started(self) -> bool:
        pid = self._pid_provider()
        with self._lock:
            if self._pid == pid and self._thread is not None and self._thread.is_alive():
                return False
            stop_event = Event()
            self._stop_event = stop_event
            self._pid = pid
            self._next_due = None
            thread = Thread(
                target=self._run,
                args=(pid, stop_event),
                name=f'ada-alarm-collector-{pid}', daemon=True,
            )
            self._thread = thread
            thread.start()
        return True

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError('Stop timeout must be positive')
        with self._lock:
            if self._pid != self._pid_provider():
                return
            event, thread = self._stop_event, self._thread
        if event is None or thread is None:
            return
        event.set()
        thread.join(timeout_seconds)
        if thread.is_alive():
            return
        with self._lock:
            if self._thread is thread:
                self._thread = None
                self._stop_event = None
                self._pid = None
                self._next_due = None

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def poll_due(self, *, now: float | None = None) -> AlarmCollectorPollCycle:
        instant = self._clock() if now is None else now
        if (
            isinstance(instant, bool) or not isinstance(instant, int | float)
            or not math.isfinite(instant)
        ):
            raise TypeError('Poll clock must be finite')
        if not self._poll_lock.acquire(blocking=False):
            return AlarmCollectorPollCycle(refreshed=False)
        try:
            if self._next_due is not None and instant < self._next_due:
                return AlarmCollectorPollCycle(refreshed=False)
            self._next_due = instant + self._settings.interval_seconds
            try:
                self._collector.refresh()
            except Exception as error:
                self._report_failure(error)
                return AlarmCollectorPollCycle(refreshed=True, error=error)
            self._last_incident = None
            return AlarmCollectorPollCycle(refreshed=True)
        finally:
            if now is None and self._next_due is not None:
                completed = self._clock()
                if completed >= self._next_due:
                    skipped = math.floor(
                        (completed - self._next_due) / self._settings.interval_seconds
                    ) + 1
                    self._next_due += skipped * self._settings.interval_seconds
            self._poll_lock.release()

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def _run(self, pid: int, stop_event: Event) -> None:
        try:
            while not stop_event.is_set():
                if self._pid_provider() != pid:
                    return
                self.poll_due()
                with self._poll_lock:
                    seconds = (
                        0.0 if self._next_due is None
                        else max(0.0, self._next_due - self._clock())
                    )
                stop_event.wait(seconds)
        except Exception as error:
            self._observability.critical(
                'web.alarm_collector.runtime_failed',
                'Alarm collector polling runtime failed', exception=error,
            )

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def _report_failure(self, error: Exception) -> None:
        signature = f'{type(error).__name__}:{str(error)}'
        if signature == self._last_incident:
            return
        self._last_incident = signature
        if isinstance(error, AlarmLiveReadError):
            self._observability.warning(
                'web.alarm_collector.delivery_unavailable',
                'Alarm Live source is unavailable', error_type=type(error).__name__,
            )
        elif isinstance(error, AlarmLiveContractError):
            self._observability.error(
                'web.alarm_collector.contract_failed',
                'Alarm Live document is invalid', exception=error,
            )
        else:
            self._observability.error(
                'web.alarm_collector.refresh_failed',
                'Alarm collector refresh failed', exception=error,
            )
