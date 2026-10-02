from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Protocol

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import project_kpi_latest
from ada.kpis.materialization import LocalKpiRegistryStore, require_tool_key
from ada.kpis.persistence import KpiCommitState, KpiEvaluationBatch
from ada.processes.kpi_delivery.adapter import delivery_values_from_batch
from ada.processes.kpi_delivery.configuration import (
    FrozenKpiDeliveryConfiguration,
    load_frozen_delivery_configurations,
)
from ada.processes.kpi_delivery.errors import (
    KpiDeliveryConfigurationError,
    KpiDeliveryPublicationError,
    KpiDeliveryReadinessPending,
    KpiDeliveryRepositoryError,
)
from ada.processes.kpi_delivery.models import (
    KpiDeliveryCheckpoint,
    KpiLatestDeliveryIterationResult,
    KpiLatestDeliveryIterationStatus,
    KpiLatestPublicationStatus,
)
from ada.processes.kpi_delivery.parallel import (
    KpiLatestPublicationTask,
    KpiLatestToolPublicationResult,
)
from atlanticus.runtime import JobRuntimeContext

READINESS_RETRY_SECONDS = 30.0


class _CommitStateReader(Protocol):
    def read(self) -> KpiCommitState: ...


class _EvaluationReader(Protocol):
    def read(self, watermark: KpiWatermark) -> KpiEvaluationBatch | None: ...


class _CheckpointStore(Protocol):
    def read(self, tool_key: str) -> KpiDeliveryCheckpoint | None: ...

    def commit(
        self,
        tool_key: str,
        checkpoint: KpiDeliveryCheckpoint,
    ) -> KpiDeliveryCheckpoint: ...


class _ParallelPublisher(Protocol):
    def publish(
        self,
        tasks: tuple[KpiLatestPublicationTask, ...],
    ) -> tuple[KpiLatestToolPublicationResult, ...]: ...


class KpiLatestDeliveryRuntimeJob:
    def __init__(
        self,
        *,
        store: LocalKpiRegistryStore,
        expected_tool_keys: Iterable[str],
        kpi_state: _CommitStateReader,
        evaluations: _EvaluationReader,
        checkpoints: _CheckpointStore,
        publisher: _ParallelPublisher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, LocalKpiRegistryStore):
            raise TypeError('store must be LocalKpiRegistryStore')
        expected = tuple(sorted({require_tool_key(value) for value in expected_tool_keys}))
        if not expected:
            raise ValueError('expected_tool_keys must contain at least one tool')
        self._store = store
        self._expected_tool_keys = expected
        self._kpi_state = kpi_state
        self._evaluations = evaluations
        self._checkpoints = checkpoints
        self._publisher = publisher
        self._now = now
        self._job: KpiLatestDeliveryJob | None = None

    def run_iteration(
        self,
        context: JobRuntimeContext,
    ) -> KpiLatestDeliveryIterationResult:
        if self._job is None:
            try:
                configurations = load_frozen_delivery_configurations(
                    store=self._store,
                    expected_tool_keys=self._expected_tool_keys,
                )
            except KpiDeliveryReadinessPending:
                context.set_iteration_fact('outcome', 'waiting')
                context.set_iteration_fact(
                    'reason',
                    KpiLatestDeliveryIterationStatus.MATERIALIZATION_PENDING.value,
                )
                context.set_iteration_fact('tool_count', len(self._expected_tool_keys))
                context.set_next_iteration_delay(READINESS_RETRY_SECONDS)
                return KpiLatestDeliveryIterationResult(
                    status=KpiLatestDeliveryIterationStatus.MATERIALIZATION_PENDING,
                    tool_count=len(self._expected_tool_keys),
                )
            self._job = KpiLatestDeliveryJob(
                configurations=configurations,
                kpi_state=self._kpi_state,
                evaluations=self._evaluations,
                checkpoints=self._checkpoints,
                publisher=self._publisher,
                now=self._now,
            )
        return self._job.run_iteration(context)


class KpiLatestDeliveryJob:
    def __init__(
        self,
        *,
        configurations: Mapping[str, FrozenKpiDeliveryConfiguration],
        kpi_state: _CommitStateReader,
        evaluations: _EvaluationReader,
        checkpoints: _CheckpointStore,
        publisher: _ParallelPublisher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configurations, Mapping) or not configurations:
            raise ValueError('configurations must contain at least one tool')
        for value, method_name, field_name in (
            (kpi_state, 'read', 'kpi_state'),
            (evaluations, 'read', 'evaluations'),
            (checkpoints, 'read', 'checkpoints'),
            (checkpoints, 'commit', 'checkpoints'),
            (publisher, 'publish', 'publisher'),
        ):
            if not callable(getattr(value, method_name, None)):
                raise TypeError(f'{field_name} must provide a callable {method_name} method')
        if now is not None and not callable(now):
            raise TypeError('now must be callable or None')
        self._configurations = dict(sorted(configurations.items()))
        self._kpi_state = kpi_state
        self._evaluations = evaluations
        self._checkpoint_store = checkpoints
        self._publisher = publisher
        self._now = now or _utc_now
        self._checkpoints: dict[str, KpiDeliveryCheckpoint | None] | None = None

    def run_iteration(self, context: JobRuntimeContext) -> KpiLatestDeliveryIterationResult:
        context.raise_if_cancelled()
        committed = self._kpi_state.read().watermark
        if committed is None:
            return self._record(
                context,
                KpiLatestDeliveryIterationResult(
                    status=KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING,
                    tool_count=len(self._configurations),
                ),
            )

        pending = self._pending_tools(committed)
        if not pending:
            return self._record(
                context,
                KpiLatestDeliveryIterationResult(
                    status=KpiLatestDeliveryIterationStatus.SKIPPED_CURRENT,
                    watermark_utc=committed.to_text(),
                    tool_count=len(self._configurations),
                ),
            )

        batch = self._evaluations.read(committed)
        if batch is None:
            raise KpiDeliveryRepositoryError(
                'KPI evaluation batch is missing for the committed watermark'
            )
        if batch.watermark != committed:
            raise KpiDeliveryRepositoryError(
                'KPI evaluation batch does not match the committed watermark'
            )

        values = delivery_values_from_batch(batch)
        published_at = self._now()
        tasks = tuple(
            KpiLatestPublicationTask(
                tool_key=tool_key,
                snapshot=project_kpi_latest(
                    configuration=self._configurations[tool_key].configuration,
                    values=values,
                    watermark_utc=committed.timestamp_utc,
                    published_at_utc=published_at,
                ),
            )
            for tool_key in pending
        )

        context.raise_if_cancelled()
        context.assert_lease_current()
        results = self._publisher.publish(tasks)
        context.raise_if_cancelled()
        context.assert_lease_current()

        published = 0
        unchanged = 0
        failures: list[tuple[str, Exception]] = []
        for result in results:
            if not result.successful:
                if result.error is None:
                    raise RuntimeError('Failed publication result is missing its error')
                failures.append((result.tool_key, result.error))
                continue
            if result.publication is None:
                raise RuntimeError('Successful publication result is missing its publication')
            target = self._configurations[result.tool_key]
            checkpoint = KpiDeliveryCheckpoint(
                watermark=committed,
                registry_revision=target.registry_revision,
                registry_digest=target.registry_digest,
            )
            try:
                with context.fenced_mutation():
                    committed_checkpoint = self._checkpoint_store.commit(
                        result.tool_key,
                        checkpoint,
                    )
                self._current_checkpoints()[result.tool_key] = committed_checkpoint
            except KpiDeliveryRepositoryError as error:
                failures.append((result.tool_key, error))
                continue
            context.mark_iteration_work()
            if result.publication.status is KpiLatestPublicationStatus.PUBLISHED:
                published += 1
                context.increment_execution_counter('snapshots_published')
            else:
                unchanged += 1

        result = KpiLatestDeliveryIterationResult(
            status=(
                KpiLatestDeliveryIterationStatus.PUBLISHED
                if published
                else KpiLatestDeliveryIterationStatus.UNCHANGED
            ),
            watermark_utc=committed.to_text(),
            tool_count=len(self._configurations),
            pending_tool_count=len(pending),
            published_tool_count=published,
            unchanged_tool_count=unchanged,
            failed_tool_count=len(failures),
        )
        self._record(context, result)
        if failures:
            failed = ', '.join(tool_key for tool_key, _ in failures)
            raise KpiDeliveryPublicationError(
                f'KPI latest publication failed for tools: {failed}'
            ) from failures[0][1]
        return result

    def _pending_tools(self, committed: KpiWatermark) -> tuple[str, ...]:
        pending: list[str] = []
        checkpoints = self._current_checkpoints()
        for tool_key, target in self._configurations.items():
            checkpoint = checkpoints[tool_key]
            if checkpoint is not None:
                if committed < checkpoint.watermark:
                    raise KpiDeliveryRepositoryError(
                        f'KPI committed watermark regressed behind {tool_key} checkpoint'
                    )
                if (
                    checkpoint.registry_revision == target.registry_revision
                    and checkpoint.registry_digest != target.registry_digest
                ):
                    raise KpiDeliveryConfigurationError(
                        f'KPI Registry content changed without a new revision for {tool_key}'
                    )
            if (
                checkpoint is None
                or checkpoint.watermark != committed
                or checkpoint.registry_revision != target.registry_revision
            ):
                pending.append(tool_key)
        return tuple(pending)

    def _current_checkpoints(self) -> dict[str, KpiDeliveryCheckpoint | None]:
        if self._checkpoints is None:
            self._checkpoints = {
                tool_key: self._checkpoint_store.read(tool_key) for tool_key in self._configurations
            }
        return self._checkpoints

    @staticmethod
    def _record(
        context: JobRuntimeContext,
        result: KpiLatestDeliveryIterationResult,
    ) -> KpiLatestDeliveryIterationResult:
        if result.status is KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING:
            outcome = 'empty'
        elif result.status is KpiLatestDeliveryIterationStatus.SKIPPED_CURRENT:
            outcome = 'skipped'
        else:
            outcome = 'completed'
        context.set_iteration_fact('outcome', outcome)
        context.set_iteration_fact('reason', result.status.value)
        context.set_iteration_fact('tool_count', result.tool_count)
        context.set_iteration_fact('pending_tool_count', result.pending_tool_count)
        context.set_iteration_fact('published_tool_count', result.published_tool_count)
        context.set_iteration_fact('unchanged_tool_count', result.unchanged_tool_count)
        context.set_iteration_fact('failed_tool_count', result.failed_tool_count)
        if result.watermark_utc is not None:
            context.set_iteration_fact(
                'kpi_committed_watermark_utc',
                result.watermark_utc,
            )
            context.set_execution_fact(
                'kpi_committed_watermark_utc',
                result.watermark_utc,
            )
        return result


def _utc_now() -> datetime:
    return datetime.now(UTC)
