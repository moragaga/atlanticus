from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import align_timeseries_end, project_kpi_timeseries
from ada.kpis.history import KpiHistorianAuthority
from ada.kpis.materialization import LocalKpiRegistryStore, require_tool_key
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
    KpiTimeseriesDeliveryPublicationError,
    KpiTimeseriesDeliveryReadinessPending,
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesCheckpoint,
    KpiTimeseriesDeliveryIterationResult,
    KpiTimeseriesDeliveryIterationStatus,
    KpiTimeseriesPublicationStatus,
)
from ada.processes.kpi_timeseries_delivery.parallel import (
    KpiTimeseriesPublicationTask,
    KpiTimeseriesToolPublicationResult,
)
from ada.processes.kpi_timeseries_delivery.planning import (
    FrozenKpiTimeseriesConfiguration,
    KpiTimeseriesReadPlan,
    build_timeseries_read_plan,
    load_frozen_timeseries_configurations,
)
from ada.processes.kpi_timeseries_delivery.rolling import (
    KpiTimeseriesRollingSlice,
)
from atlanticus.runtime import JobRuntimeContext

READINESS_RETRY_SECONDS = 30.0


class _AuthorityReader(Protocol):
    def read(self) -> KpiHistorianAuthority | None: ...


class _RollingReader(Protocol):
    def read(
        self,
        *,
        authority: KpiHistorianAuthority,
        keys: tuple[str, ...],
        start_utc: datetime,
        end_utc: datetime,
    ) -> KpiTimeseriesRollingSlice: ...


class _CheckpointStore(Protocol):
    def read(self, tool_key: str) -> KpiTimeseriesCheckpoint | None: ...

    def commit(
        self,
        tool_key: str,
        checkpoint: KpiTimeseriesCheckpoint,
    ) -> KpiTimeseriesCheckpoint: ...


class _ParallelPublisher(Protocol):
    def publish(
        self,
        tasks: tuple[KpiTimeseriesPublicationTask, ...],
    ) -> tuple[KpiTimeseriesToolPublicationResult, ...]: ...


class KpiTimeseriesDeliveryRuntimeJob:
    def __init__(
        self,
        *,
        store: LocalKpiRegistryStore,
        expected_tool_keys: Iterable[str],
        historian: _AuthorityReader,
        rolling: _RollingReader,
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
        self._historian = historian
        self._rolling = rolling
        self._checkpoints = checkpoints
        self._publisher = publisher
        self._now = now
        self._job: KpiTimeseriesDeliveryJob | None = None

    def run_iteration(
        self,
        context: JobRuntimeContext,
    ) -> KpiTimeseriesDeliveryIterationResult:
        if self._job is None:
            try:
                configurations = load_frozen_timeseries_configurations(
                    store=self._store,
                    expected_tool_keys=self._expected_tool_keys,
                )
            except KpiTimeseriesDeliveryReadinessPending:
                context.set_iteration_fact('outcome', 'waiting')
                context.set_iteration_fact(
                    'reason',
                    KpiTimeseriesDeliveryIterationStatus.MATERIALIZATION_PENDING.value,
                )
                context.set_iteration_fact('tool_count', len(self._expected_tool_keys))
                context.set_next_iteration_delay(READINESS_RETRY_SECONDS)
                return KpiTimeseriesDeliveryIterationResult(
                    status=KpiTimeseriesDeliveryIterationStatus.MATERIALIZATION_PENDING,
                    tool_count=len(self._expected_tool_keys),
                )
            self._job = KpiTimeseriesDeliveryJob(
                configurations=configurations,
                read_plan=build_timeseries_read_plan(configurations),
                historian=self._historian,
                rolling=self._rolling,
                checkpoints=self._checkpoints,
                publisher=self._publisher,
                now=self._now,
            )
        return self._job.run_iteration(context)


class KpiTimeseriesDeliveryJob:
    def __init__(
        self,
        *,
        configurations: Mapping[str, FrozenKpiTimeseriesConfiguration],
        read_plan: KpiTimeseriesReadPlan,
        historian: _AuthorityReader,
        rolling: _RollingReader,
        checkpoints: _CheckpointStore,
        publisher: _ParallelPublisher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configurations, Mapping) or not configurations:
            raise ValueError('configurations must contain at least one tool')
        if not isinstance(read_plan, KpiTimeseriesReadPlan):
            raise TypeError('read_plan must be KpiTimeseriesReadPlan')
        for value, method_name, field_name in (
            (historian, 'read', 'historian'),
            (rolling, 'read', 'rolling'),
            (checkpoints, 'read', 'checkpoints'),
            (checkpoints, 'commit', 'checkpoints'),
            (publisher, 'publish', 'publisher'),
        ):
            if not callable(getattr(value, method_name, None)):
                raise TypeError(f'{field_name} must provide a callable {method_name} method')
        if now is not None and not callable(now):
            raise TypeError('now must be callable or None')
        self._configurations = dict(sorted(configurations.items()))
        self._read_plan = read_plan
        self._historian = historian
        self._rolling = rolling
        self._checkpoint_store = checkpoints
        self._publisher = publisher
        self._now = now or _utc_now
        self._checkpoints: dict[str, KpiTimeseriesCheckpoint | None] | None = None

    def run_iteration(
        self,
        context: JobRuntimeContext,
    ) -> KpiTimeseriesDeliveryIterationResult:
        context.raise_if_cancelled()
        authority = self._historian.read()
        if authority is None:
            if any(value is not None for value in self._current_checkpoints().values()):
                raise KpiTimeseriesDeliveryRepositoryError(
                    'KPI historian authority is missing after timeseries delivery progress'
                )
            return self._record(
                context,
                KpiTimeseriesDeliveryIterationResult(
                    status=KpiTimeseriesDeliveryIterationStatus.HISTORIAN_WATERMARK_MISSING,
                    tool_count=len(self._configurations),
                ),
            )

        aligned_end = align_timeseries_end(authority.watermark_utc)
        watermark = KpiWatermark(aligned_end)
        pending = self._pending_tools(watermark)
        if not pending:
            return self._record(
                context,
                KpiTimeseriesDeliveryIterationResult(
                    status=KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT,
                    watermark_utc=watermark.to_text(),
                    historian_revision=authority.revision,
                    tool_count=len(self._configurations),
                ),
            )

        histories = {}
        if self._read_plan.max_window_hours > 0:
            rolling = self._rolling.read(
                authority=authority,
                keys=self._read_plan.required_columns,
                start_utc=aligned_end - timedelta(hours=self._read_plan.max_window_hours),
                end_utc=aligned_end,
            )
            histories = rolling.histories

        published_at = self._now()
        tasks = tuple(
            KpiTimeseriesPublicationTask(
                tool_key=tool_key,
                snapshot=project_kpi_timeseries(
                    configuration=self._configurations[tool_key].configuration,
                    histories=histories,
                    historian_revision=authority.revision,
                    end_utc=aligned_end,
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
            checkpoint = KpiTimeseriesCheckpoint(
                watermark=watermark,
                registry_revision=target.registry_revision,
                registry_digest=target.registry_digest,
            )
            try:
                with context.fenced_mutation():
                    committed = self._checkpoint_store.commit(
                        result.tool_key,
                        checkpoint,
                    )
                self._current_checkpoints()[result.tool_key] = committed
            except KpiTimeseriesDeliveryRepositoryError as error:
                failures.append((result.tool_key, error))
                continue
            context.mark_iteration_work()
            if result.publication.status is KpiTimeseriesPublicationStatus.PUBLISHED:
                published += 1
                context.increment_execution_counter('snapshots_published')
            else:
                unchanged += 1

        iteration_result = KpiTimeseriesDeliveryIterationResult(
            status=(
                KpiTimeseriesDeliveryIterationStatus.PUBLISHED
                if published
                else KpiTimeseriesDeliveryIterationStatus.UNCHANGED
            ),
            watermark_utc=watermark.to_text(),
            historian_revision=authority.revision,
            tool_count=len(self._configurations),
            pending_tool_count=len(pending),
            published_tool_count=published,
            unchanged_tool_count=unchanged,
            failed_tool_count=len(failures),
        )
        self._record(context, iteration_result)
        if failures:
            failed = ', '.join(tool_key for tool_key, _ in failures)
            raise KpiTimeseriesDeliveryPublicationError(
                f'KPI timeseries publication failed for tools: {failed}'
            ) from failures[0][1]
        return iteration_result

    def _pending_tools(self, watermark: KpiWatermark) -> tuple[str, ...]:
        pending: list[str] = []
        checkpoints = self._current_checkpoints()
        for tool_key, target in self._configurations.items():
            checkpoint = checkpoints[tool_key]
            if checkpoint is not None:
                if watermark < checkpoint.watermark:
                    raise KpiTimeseriesDeliveryRepositoryError(
                        f'KPI historian authority regressed behind {tool_key} checkpoint'
                    )
                if (
                    checkpoint.registry_revision == target.registry_revision
                    and checkpoint.registry_digest != target.registry_digest
                ):
                    raise KpiTimeseriesDeliveryConfigurationError(
                        f'KPI Registry content changed without a new revision for {tool_key}'
                    )
            if (
                checkpoint is None
                or checkpoint.watermark != watermark
                or checkpoint.registry_revision != target.registry_revision
            ):
                pending.append(tool_key)
        return tuple(pending)

    def _current_checkpoints(self) -> dict[str, KpiTimeseriesCheckpoint | None]:
        if self._checkpoints is None:
            self._checkpoints = {
                tool_key: self._checkpoint_store.read(tool_key) for tool_key in self._configurations
            }
        return self._checkpoints

    @staticmethod
    def _record(
        context: JobRuntimeContext,
        result: KpiTimeseriesDeliveryIterationResult,
    ) -> KpiTimeseriesDeliveryIterationResult:
        if result.status is KpiTimeseriesDeliveryIterationStatus.HISTORIAN_WATERMARK_MISSING:
            outcome = 'empty'
        elif result.status is KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT:
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
            context.set_iteration_fact('timeseries_end_utc', result.watermark_utc)
            context.set_execution_fact('timeseries_end_utc', result.watermark_utc)
        if result.historian_revision is not None:
            context.set_iteration_fact(
                'historian_revision',
                result.historian_revision,
            )
            context.set_execution_fact(
                'historian_revision',
                result.historian_revision,
            )
        return result


def _utc_now() -> datetime:
    return datetime.now(UTC)
