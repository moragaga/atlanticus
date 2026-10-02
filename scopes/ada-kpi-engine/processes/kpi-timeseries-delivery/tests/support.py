from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import KpiDeliveryBinding, KpiDeliveryConfiguration
from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesPublication,
    KpiTimeseriesPublicationStatus,
)


class RuntimeContextStub:
    def __init__(self) -> None:
        self.iteration_facts: dict[str, object] = {}
        self.execution_facts: dict[str, object] = {}
        self.execution_counters: dict[str, float] = {}
        self.work = False
        self.lease_checks = 0
        self.fences = 0

    def raise_if_cancelled(self) -> None:
        pass

    def assert_lease_current(self) -> None:
        self.lease_checks += 1

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield

    def mark_iteration_work(self) -> None:
        self.work = True

    def set_iteration_fact(self, key: str, value: object) -> None:
        self.iteration_facts[key] = value

    def set_execution_fact(self, key: str, value: object) -> None:
        self.execution_facts[key] = value

    def increment_execution_counter(self, key: str, amount: int | float = 1) -> None:
        self.execution_counters[key] = self.execution_counters.get(key, 0) + amount


class AuthorityReader:
    def __init__(self, authority: KpiHistorianAuthority | None) -> None:
        self.authority = authority

    def read(self) -> KpiHistorianAuthority | None:
        return self.authority


class HistoryReader:
    def __init__(self, histories=None) -> None:
        self.histories = {} if histories is None else histories
        self.calls = 0

    def read_histories(self, *, keys, start_utc, end_utc):
        self.calls += 1
        return self.histories


class CheckpointStore:
    def __init__(self, value=None, events=None) -> None:
        self.value = value
        self.events = [] if events is None else events
        self.commit_calls = 0

    def read(self):
        return self.value

    def commit(self, checkpoint):
        self.commit_calls += 1
        self.events.append('checkpoint')
        self.value = checkpoint
        return checkpoint


class SnapshotPublisher:
    def __init__(self, *, status=KpiTimeseriesPublicationStatus.PUBLISHED, events=None) -> None:
        self.status = status
        self.events = [] if events is None else events
        self.calls = 0
        self.error = None

    def publish(self, snapshot):
        self.calls += 1
        self.events.append('publish')
        if self.error is not None:
            raise self.error
        return KpiTimeseriesPublication(
            status=self.status,
            revision=snapshot.manifest.revision,
        )


def configuration(revision: str = 'config-r1') -> KpiDeliveryConfiguration:
    return KpiDeliveryConfiguration(
        revision=revision,
        tool_projection_revision='tools-r1',
        bindings=(
            KpiDeliveryBinding(
                key='produccion_total',
                destination_keys=('global_indicators',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=1,
            ),
        ),
    )


def authority(minute: int = 3) -> KpiHistorianAuthority:
    return KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 5, minute, tzinfo=UTC))


def watermark(minute: int) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 9, 1, 5, minute, tzinfo=UTC))
