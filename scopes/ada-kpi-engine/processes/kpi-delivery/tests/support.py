from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

from ada.kpis.core import (
    KpiEvaluation,
    KpiResult,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from ada.kpis.delivery import KpiDeliveryBinding, KpiDeliveryConfiguration
from ada.kpis.persistence import KpiCommitState, KpiEvaluationBatch
from ada.processes.kpi_delivery.configuration import FrozenKpiDeliveryConfiguration
from ada.processes.kpi_delivery.models import (
    KpiDeliveryCheckpoint,
    KpiLatestPublication,
    KpiLatestPublicationStatus,
)
from ada.processes.kpi_delivery.parallel import (
    KpiLatestPublicationTask,
    KpiLatestToolPublicationResult,
)


class RuntimeContextStub:
    def __init__(self) -> None:
        self.iteration_facts: dict[str, object] = {}
        self.execution_facts: dict[str, object] = {}
        self.execution_counters: dict[str, float] = {}
        self.work = False
        self.cancel_checks = 0
        self.lease_checks = 0
        self.fences = 0

    def raise_if_cancelled(self) -> None:
        self.cancel_checks += 1

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


class CommitStateReader:
    def __init__(self, watermark_value: KpiWatermark | None) -> None:
        self.watermark = watermark_value
        self.calls = 0

    def read(self) -> KpiCommitState:
        self.calls += 1
        return KpiCommitState(self.watermark)


class EvaluationReader:
    def __init__(self, source_batch: KpiEvaluationBatch | None) -> None:
        self.batch = source_batch
        self.calls = 0
        self.watermarks = []

    def read(self, watermark_value: KpiWatermark) -> KpiEvaluationBatch | None:
        self.calls += 1
        self.watermarks.append(watermark_value)
        return self.batch


class CheckpointStore:
    def __init__(self, values=None, events=None) -> None:
        self.values = {} if values is None else dict(values)
        self.read_calls = []
        self.commit_calls = []
        self.events = [] if events is None else events

    def read(self, tool_key: str) -> KpiDeliveryCheckpoint | None:
        self.read_calls.append(tool_key)
        return self.values.get(tool_key)

    def commit(
        self,
        tool_key: str,
        checkpoint: KpiDeliveryCheckpoint,
    ) -> KpiDeliveryCheckpoint:
        self.commit_calls.append((tool_key, checkpoint))
        self.events.append(f'checkpoint:{tool_key}')
        self.values[tool_key] = checkpoint
        return checkpoint


class SnapshotPublisher:
    def __init__(
        self,
        tool_key: str = 'tool',
        *,
        status=KpiLatestPublicationStatus.PUBLISHED,
        events=None,
    ) -> None:
        self.tool_key = tool_key
        self.status = status
        self.calls = 0
        self.snapshots = []
        self.events = [] if events is None else events
        self.error: Exception | None = None

    def publish(self, snapshot) -> KpiLatestPublication:
        self.calls += 1
        self.snapshots.append(snapshot)
        label = 'publish' if self.tool_key == 'tool' else f'publish:{self.tool_key}'
        self.events.append(label)
        if self.error is not None:
            raise self.error
        return KpiLatestPublication(
            status=self.status,
            revision=snapshot.manifest.revision,
        )


class ParallelPublisherStub:
    def __init__(self, publishers) -> None:
        self.publishers = publishers
        self.calls = 0
        self.tasks = []

    def publish(
        self,
        tasks: tuple[KpiLatestPublicationTask, ...],
    ) -> tuple[KpiLatestToolPublicationResult, ...]:
        self.calls += 1
        self.tasks.append(tasks)
        results = []
        for task in tasks:
            publisher = self.publishers[task.tool_key]
            try:
                publication = publisher.publish(task.snapshot)
                results.append(
                    KpiLatestToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=publication,
                        error=None,
                    )
                )
            except Exception as error:
                results.append(
                    KpiLatestToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=None,
                        error=error,
                    )
                )
        return tuple(results)


def watermark(minute: int = 0) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 9, 1, 5, minute, tzinfo=UTC))


def evaluation(
    key: str,
    *,
    status: KpiStatus = KpiStatus.OK,
    value_kind: KpiValueKind = KpiValueKind.VALUE,
    value='42.5',
    parsed_value=None,
    value_type: KpiValueType | None = KpiValueType.FLOAT,
    error: str | None = None,
    watermark_value: KpiWatermark | None = None,
) -> KpiEvaluation:
    resolved_watermark = watermark() if watermark_value is None else watermark_value
    if value_kind is KpiValueKind.JSON:
        value_type = None
        parsed_value = None
    elif status is KpiStatus.OK:
        if not isinstance(value, str):
            value = str(value)
        if parsed_value is None:
            parsed_value = value.replace('.', ',')
    if status is KpiStatus.OK:
        result = KpiResult(
            status=status,
            value_kind=value_kind,
            value=value,
            parsed_value=parsed_value,
            value_type=value_type,
        )
    elif status is KpiStatus.MISSING:
        result = KpiResult(
            status=status,
            value_kind=value_kind,
            value_type=value_type,
        )
    else:
        result = KpiResult(
            status=status,
            value_kind=value_kind,
            value_type=value_type,
            error='TestError' if error is None else error,
        )
    return KpiEvaluation(
        key=key,
        area='general',
        watermark=resolved_watermark,
        evaluated_at_utc=resolved_watermark.timestamp_utc,
        result=result,
    )


def batch(*evaluations: KpiEvaluation) -> KpiEvaluationBatch:
    return KpiEvaluationBatch(
        watermark=evaluations[0].watermark,
        evaluations=evaluations,
    )


def configuration(
    revision: str = 'registry-r1',
    *,
    key: str = 'produccion_total',
    destination: str = 'global_indicators',
    latest_enabled: bool = True,
    destinations: tuple[str, ...] | None = None,
) -> KpiDeliveryConfiguration:
    resolved_destinations = (destination,) if destinations is None else destinations
    return KpiDeliveryConfiguration(
        revision=revision,
        tool_projection_revision='tools-r1',
        bindings=(
            KpiDeliveryBinding(
                key=key,
                destination_keys=resolved_destinations,
                latest_enabled=latest_enabled,
                series_enabled=False,
                series_hours=None,
            ),
        ),
    )


def frozen(
    tool_key: str,
    *,
    revision: str = 'registry-r1',
    digest: str | None = None,
    key: str = 'produccion_total',
) -> FrozenKpiDeliveryConfiguration:
    resolved_digest = digest or (tool_key[0] * 64)
    return FrozenKpiDeliveryConfiguration(
        tool_key=tool_key,
        registry_revision=revision,
        registry_digest=resolved_digest,
        configuration=configuration(revision, key=key),
    )


def checkpoint(
    minute: int,
    *,
    revision: str = 'registry-r1',
    digest: str = 'a' * 64,
) -> KpiDeliveryCheckpoint:
    return KpiDeliveryCheckpoint(
        watermark=watermark(minute),
        registry_revision=revision,
        registry_digest=digest,
    )
