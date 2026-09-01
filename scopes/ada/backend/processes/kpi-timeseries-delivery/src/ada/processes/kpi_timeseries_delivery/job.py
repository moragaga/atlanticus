from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import (
    KpiDeliveryConfiguration,
    align_timeseries_end,
    project_kpi_timeseries,
)
from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesCheckpoint,
    KpiTimeseriesDeliveryIterationResult,
    KpiTimeseriesDeliveryIterationStatus,
    KpiTimeseriesPublication,
    KpiTimeseriesPublicationStatus,
)
from atlanticus.runtime import JobRuntimeContext


class _AuthorityReader(Protocol):
    def read(self) -> KpiHistorianAuthority | None: ...


class _HistoryReader(Protocol):
    def read_histories(
        self,
        *,
        keys: tuple[str, ...],
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, dict[datetime, object]]: ...


class _CheckpointStore(Protocol):
    def read(self) -> KpiTimeseriesCheckpoint | None: ...

    def commit(self, checkpoint: KpiTimeseriesCheckpoint) -> KpiTimeseriesCheckpoint: ...


class _SnapshotPublisher(Protocol):
    def publish(self, snapshot) -> KpiTimeseriesPublication: ...


class KpiTimeseriesDeliveryJob:
    def __init__(
        self,
        *,
        configuration: KpiDeliveryConfiguration,
        historian: _AuthorityReader,
        history: _HistoryReader,
        checkpoint: _CheckpointStore,
        snapshots: _SnapshotPublisher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configuration, KpiDeliveryConfiguration):
            raise TypeError('configuration must be KpiDeliveryConfiguration')
        for value, method_name, field_name in (
            (historian, 'read', 'historian'),
            (history, 'read_histories', 'history'),
            (checkpoint, 'read', 'checkpoint'),
            (checkpoint, 'commit', 'checkpoint'),
            (snapshots, 'publish', 'snapshots'),
        ):
            if not callable(getattr(value, method_name, None)):
                raise TypeError(f'{field_name} must provide a callable {method_name} method')
        if now is not None and not callable(now):
            raise TypeError('now must be callable or None')
        self._configuration = configuration
        self._historian = historian
        self._history = history
        self._checkpoint_store = checkpoint
        self._snapshots = snapshots
        self._now = now or _utc_now
        self._checkpoint_loaded = False
        self._checkpoint: KpiTimeseriesCheckpoint | None = None

    def run_iteration(self, context: JobRuntimeContext) -> KpiTimeseriesDeliveryIterationResult:
        context.raise_if_cancelled()
        checkpoint = self._current_checkpoint()
        authority = self._historian.read()
        if authority is None:
            if checkpoint is not None:
                raise KpiTimeseriesDeliveryRepositoryError(
                    'KPI historian authority is missing after timeseries delivery progress'
                )
            return _record_result(
                context,
                KpiTimeseriesDeliveryIterationResult(
                    status=KpiTimeseriesDeliveryIterationStatus.HISTORIAN_WATERMARK_MISSING,
                    configuration_revision=self._configuration.revision,
                ),
            )

        historian_watermark = KpiWatermark(authority.watermark_utc)
        aligned_end = align_timeseries_end(historian_watermark.timestamp_utc)
        timeseries_watermark = KpiWatermark(aligned_end)
        _validate_authority(
            checkpoint=checkpoint,
            timeseries_watermark=timeseries_watermark,
        )
        if _is_current(
            checkpoint=checkpoint,
            timeseries_watermark=timeseries_watermark,
            configuration_revision=self._configuration.revision,
        ):
            return _record_result(
                context,
                KpiTimeseriesDeliveryIterationResult(
                    status=KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT,
                    configuration_revision=self._configuration.revision,
                    watermark_utc=_watermark_text(aligned_end),
                    historian_revision=authority.revision,
                ),
            )

        series_bindings = tuple(
            binding for binding in self._configuration.bindings if binding.series_enabled
        )
        max_hours = max(
            (binding.series_hours or 0 for binding in series_bindings),
            default=0,
        )
        keys = tuple(binding.key for binding in series_bindings)
        histories: dict[str, dict[datetime, object]] = {}
        if max_hours > 0:
            histories = self._history.read_histories(
                keys=keys,
                start_utc=aligned_end - timedelta(hours=max_hours),
                end_utc=aligned_end,
            )

        context.raise_if_cancelled()
        snapshot = project_kpi_timeseries(
            configuration=self._configuration,
            histories=histories,
            historian_revision=authority.revision,
            end_utc=aligned_end,
            published_at_utc=self._now(),
        )
        context.raise_if_cancelled()
        context.assert_lease_current()
        publication = self._snapshots.publish(snapshot)
        context.raise_if_cancelled()
        context.assert_lease_current()

        new_checkpoint = KpiTimeseriesCheckpoint(
            watermark=timeseries_watermark,
            configuration_revision=self._configuration.revision,
        )
        with context.fenced_mutation():
            committed_checkpoint = self._checkpoint_store.commit(new_checkpoint)
        self._checkpoint = committed_checkpoint
        self._checkpoint_loaded = True

        status = (
            KpiTimeseriesDeliveryIterationStatus.PUBLISHED
            if publication.status is KpiTimeseriesPublicationStatus.PUBLISHED
            else KpiTimeseriesDeliveryIterationStatus.UNCHANGED
        )
        return _record_result(
            context,
            KpiTimeseriesDeliveryIterationResult(
                status=status,
                configuration_revision=self._configuration.revision,
                watermark_utc=snapshot.end_utc,
                historian_revision=authority.revision,
                delivery_revision=publication.revision,
                destination_count=len(snapshot.destinations),
                series_count=len(snapshot.series),
            ),
        )

    def _current_checkpoint(self) -> KpiTimeseriesCheckpoint | None:
        if not self._checkpoint_loaded:
            self._checkpoint = self._checkpoint_store.read()
            self._checkpoint_loaded = True
        return self._checkpoint


def _validate_authority(
    *,
    checkpoint: KpiTimeseriesCheckpoint | None,
    timeseries_watermark: KpiWatermark,
) -> None:
    if checkpoint is not None and timeseries_watermark < checkpoint.watermark:
        raise KpiTimeseriesDeliveryRepositoryError(
            'KPI historian authority must not regress behind timeseries delivery checkpoint'
        )


def _is_current(
    *,
    checkpoint: KpiTimeseriesCheckpoint | None,
    timeseries_watermark: KpiWatermark,
    configuration_revision: str,
) -> bool:
    return (
        checkpoint is not None
        and checkpoint.watermark == timeseries_watermark
        and checkpoint.configuration_revision == configuration_revision
    )


def _watermark_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _record_result(
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
    context.set_iteration_fact('configuration_revision', result.configuration_revision)
    if result.watermark_utc is not None:
        context.set_iteration_fact('timeseries_end_utc', result.watermark_utc)
        context.set_execution_fact('timeseries_end_utc', result.watermark_utc)
    if result.historian_revision is not None:
        context.set_iteration_fact('historian_revision', result.historian_revision)
        context.set_execution_fact('historian_revision', result.historian_revision)
    if result.delivery_revision is not None:
        context.set_iteration_fact('delivery_revision', result.delivery_revision)
        context.set_execution_fact('delivery_revision', result.delivery_revision)
    context.set_iteration_fact('destination_count', result.destination_count)
    context.set_iteration_fact('series_count', result.series_count)
    if outcome == 'completed':
        context.mark_iteration_work()
        if result.status is KpiTimeseriesDeliveryIterationStatus.PUBLISHED:
            context.increment_execution_counter('snapshots_published')
    return result


def _utc_now() -> datetime:
    return datetime.now(UTC)
