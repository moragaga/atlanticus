from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiTimeseriesHistory,
)
from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesCheckpoint,
    KpiTimeseriesPublication,
    KpiTimeseriesPublicationStatus,
)
from ada.processes.kpi_timeseries_delivery.parallel import (
    KpiTimeseriesToolPublicationResult,
)
from ada.processes.kpi_timeseries_delivery.planning import (
    FrozenKpiTimeseriesConfiguration,
)
from ada.processes.kpi_timeseries_delivery.rolling import (
    KpiTimeseriesRollingSlice,
)


class RuntimeContextStub:
    def __init__(self) -> None:
        self.iteration_facts: dict[str, object] = {}
        self.execution_facts: dict[str, object] = {}
        self.execution_counters: dict[str, float] = {}
        self.work = False
        self.lease_checks = 0
        self.fences = 0
        self.next_delay = None

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

    def set_next_iteration_delay(self, seconds: float) -> None:
        self.next_delay = seconds


class AuthorityReader:
    def __init__(self, value: KpiHistorianAuthority | None) -> None:
        self.value = value
        self.calls = 0

    def read(self) -> KpiHistorianAuthority | None:
        self.calls += 1
        return self.value


class RollingReader:
    def __init__(self, histories=None) -> None:
        self.histories = {} if histories is None else histories
        self.calls = []

    def read(self, *, authority, keys, start_utc, end_utc):
        self.calls.append(
            {
                'authority': authority,
                'keys': keys,
                'start_utc': start_utc,
                'end_utc': end_utc,
            }
        )
        return KpiTimeseriesRollingSlice(
            watermark_utc=authority.watermark_utc,
            historian_revision=authority.revision,
            histories=self.histories,
        )


class CheckpointStore:
    def __init__(self, values=None) -> None:
        self.values = {} if values is None else dict(values)
        self.commits = []

    def read(self, tool_key):
        return self.values.get(tool_key)

    def commit(self, tool_key, checkpoint):
        self.commits.append((tool_key, checkpoint))
        self.values[tool_key] = checkpoint
        return checkpoint


class SnapshotPublisher:
    def __init__(self, tool_key) -> None:
        self.tool_key = tool_key
        self.snapshots = []
        self.error = None
        self.status = KpiTimeseriesPublicationStatus.PUBLISHED

    def publish(self, snapshot):
        self.snapshots.append(snapshot)
        if self.error is not None:
            raise self.error
        return KpiTimeseriesPublication(
            status=self.status,
            revision=snapshot.manifest.revision,
        )


class ParallelPublisherStub:
    def __init__(self, publishers):
        self.publishers = publishers
        self.calls = 0
        self.tasks = []

    def publish(self, tasks):
        self.calls += 1
        self.tasks.append(tasks)
        results = []
        for task in tasks:
            publisher = self.publishers[task.tool_key]
            try:
                publication = publisher.publish(task.snapshot)
                results.append(
                    KpiTimeseriesToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=publication,
                        error=None,
                    )
                )
            except Exception as error:
                results.append(
                    KpiTimeseriesToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=None,
                        error=error,
                    )
                )
        return tuple(results)


def configuration(
    revision: str = 'registry-r1',
    *,
    key: str = 'produccion_total',
    hours: int = 1,
) -> KpiDeliveryConfiguration:
    return KpiDeliveryConfiguration(
        revision=revision,
        tool_projection_revision='tools-r1',
        bindings=(
            KpiDeliveryBinding(
                key=key,
                destination_keys=('global_indicators',),
                latest_enabled=True,
                series_enabled=True,
                series_hours=hours,
            ),
        ),
    )


def frozen(
    tool_key: str,
    *,
    revision: str = 'registry-r1',
    digest: str = 'a' * 64,
    key: str = 'produccion_total',
    hours: int = 1,
) -> FrozenKpiTimeseriesConfiguration:
    return FrozenKpiTimeseriesConfiguration(
        tool_key=tool_key,
        registry_revision=revision,
        registry_digest=digest,
        configuration=configuration(revision, key=key, hours=hours),
    )


def authority(minute: int = 4) -> KpiHistorianAuthority:
    return KpiHistorianAuthority(watermark_utc=datetime(2026, 9, 1, 5, minute, tzinfo=UTC))


def watermark(minute: int) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 9, 1, 5, minute, tzinfo=UTC))


def checkpoint(
    minute: int,
    *,
    revision: str = 'registry-r1',
    digest: str = 'a' * 64,
) -> KpiTimeseriesCheckpoint:
    return KpiTimeseriesCheckpoint(
        watermark=watermark(minute),
        registry_revision=revision,
        registry_digest=digest,
    )


def histories():
    return {
        'produccion_total': KpiTimeseriesHistory(
            value_type='float',
            values={datetime(2026, 9, 1, 5, 4, tzinfo=UTC): '42.5'},
        ),
        'otra': KpiTimeseriesHistory(
            value_type='integer',
            values={datetime(2026, 9, 1, 5, 4, tzinfo=UTC): '7'},
        ),
    }
