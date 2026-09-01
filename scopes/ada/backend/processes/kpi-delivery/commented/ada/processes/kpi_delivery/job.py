# Orquesta Latest usando una configuración congelada por ejecución.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from ada.kpis.core import KpiWatermark
from ada.kpis.delivery import KpiDeliveryConfiguration, KpiDeliveryStatus, project_kpi_latest
from ada.kpis.persistence import KpiCommitState, KpiEvaluationBatch
from ada.processes.kpi_delivery.adapter import delivery_values_from_batch
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import (
    KpiDeliveryCheckpoint,
    KpiLatestDeliveryIterationResult,
    KpiLatestDeliveryIterationStatus,
    KpiLatestPublication,
    KpiLatestPublicationStatus,
)
from atlanticus.runtime import JobRuntimeContext

_UNSET = object()


# Mantiene aislada la responsabilidad de _CommitStateReader.
class _CommitStateReader(Protocol):
    def read(self) -> KpiCommitState: ...


# Mantiene aislada la responsabilidad de _EvaluationReader.
class _EvaluationReader(Protocol):
    def read(self, watermark: KpiWatermark) -> KpiEvaluationBatch | None: ...


# Mantiene aislada la responsabilidad de _CheckpointStore.
class _CheckpointStore(Protocol):
    def read(self) -> KpiDeliveryCheckpoint | None: ...

    def commit(self, checkpoint: KpiDeliveryCheckpoint) -> KpiDeliveryCheckpoint: ...


# Mantiene aislada la responsabilidad de _SnapshotPublisher.
class _SnapshotPublisher(Protocol):
    def publish(self, snapshot) -> KpiLatestPublication: ...


# Recibe la configuración ya congelada y no conoce su repositorio Cosmos.
class KpiLatestDeliveryJob:
    def __init__(
        self,
        *,
        configuration: KpiDeliveryConfiguration,
        kpi_state: _CommitStateReader,
        evaluations: _EvaluationReader,
        checkpoint: _CheckpointStore,
        snapshots: _SnapshotPublisher,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(configuration, KpiDeliveryConfiguration):
            raise TypeError('configuration must be KpiDeliveryConfiguration')
        for value, method_name, field_name in (
            (kpi_state, 'read', 'kpi_state'),
            (evaluations, 'read', 'evaluations'),
            (checkpoint, 'read', 'checkpoint'),
            (checkpoint, 'commit', 'checkpoint'),
            (snapshots, 'publish', 'snapshots'),
        ):
            if not callable(getattr(value, method_name, None)):
                raise TypeError(f'{field_name} must provide a callable {method_name} method')
        if now is not None and not callable(now):
            raise TypeError('now must be callable or None')
        self._configuration = configuration
        self._kpi_state = kpi_state
        self._evaluations = evaluations
        self._checkpoint_store = checkpoint
        self._snapshots = snapshots
        self._now = now or _utc_now
        self._checkpoint: KpiDeliveryCheckpoint | None | object = _UNSET

    def run_iteration(self, context: JobRuntimeContext) -> KpiLatestDeliveryIterationResult:
        context.raise_if_cancelled()
        checkpoint = self._current_checkpoint()
        committed = self._kpi_state.read().watermark
        _validate_authority(checkpoint=checkpoint, committed=committed)
        if committed is None:
            return _record_result(
                context,
                KpiLatestDeliveryIterationResult(
                    status=KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING,
                    configuration_revision=self._configuration.revision,
                ),
            )
        if _is_current(
            checkpoint=checkpoint,
            committed=committed,
            configuration_revision=self._configuration.revision,
        ):
            return _record_result(
                context,
                KpiLatestDeliveryIterationResult(
                    status=KpiLatestDeliveryIterationStatus.SKIPPED_CURRENT,
                    watermark_utc=committed.to_text(),
                    configuration_revision=self._configuration.revision,
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
        snapshot = project_kpi_latest(
            configuration=self._configuration,
            values=values,
            watermark_utc=committed.timestamp_utc,
            published_at_utc=self._now(),
        )
        context.raise_if_cancelled()
        context.assert_lease_current()
        publication = self._snapshots.publish(snapshot)
        context.raise_if_cancelled()
        context.assert_lease_current()
        new_checkpoint = KpiDeliveryCheckpoint(
            watermark=committed,
            configuration_revision=self._configuration.revision,
        )
        with context.fenced_mutation():
            committed_checkpoint = self._checkpoint_store.commit(new_checkpoint)
        self._checkpoint = committed_checkpoint
        return _record_result(
            context,
            _publication_result(publication=publication, snapshot=snapshot),
        )

    def _current_checkpoint(self) -> KpiDeliveryCheckpoint | None:
        if self._checkpoint is _UNSET:
            self._checkpoint = self._checkpoint_store.read()
        if self._checkpoint is None:
            return None
        return self._checkpoint


# Mantiene aislada la responsabilidad de _validate_authority.
def _validate_authority(
    *,
    checkpoint: KpiDeliveryCheckpoint | None,
    committed: KpiWatermark | None,
) -> None:
    if checkpoint is None:
        return
    if committed is None:
        raise KpiDeliveryRepositoryError(
            'KPI committed watermark is missing after delivery progress'
        )
    if committed < checkpoint.watermark:
        raise KpiDeliveryRepositoryError(
            'KPI committed watermark must not regress behind delivery checkpoint'
        )


# Mantiene aislada la responsabilidad de _is_current.
def _is_current(
    *,
    checkpoint: KpiDeliveryCheckpoint | None,
    committed: KpiWatermark,
    configuration_revision: str,
) -> bool:
    return (
        checkpoint is not None
        and checkpoint.watermark == committed
        and checkpoint.configuration_revision == configuration_revision
    )


# Mantiene aislada la responsabilidad de _publication_result.
def _publication_result(
    *, publication: KpiLatestPublication, snapshot
) -> KpiLatestDeliveryIterationResult:
    values = tuple(
        value for destination in snapshot.destinations.values() for value in destination.values()
    )
    status = (
        KpiLatestDeliveryIterationStatus.PUBLISHED
        if publication.status is KpiLatestPublicationStatus.PUBLISHED
        else KpiLatestDeliveryIterationStatus.UNCHANGED
    )
    return KpiLatestDeliveryIterationResult(
        status=status,
        watermark_utc=snapshot.manifest.watermark_utc,
        configuration_revision=snapshot.manifest.configuration_revision,
        delivery_revision=publication.revision,
        destination_count=len(snapshot.destinations),
        value_count=len(values),
        missing_count=sum(value.status is KpiDeliveryStatus.MISSING for value in values),
        error_count=sum(value.status is KpiDeliveryStatus.ERROR for value in values),
    )


# Mantiene aislada la responsabilidad de _record_result.
def _record_result(
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
    context.set_iteration_fact('configuration_revision', result.configuration_revision)
    if result.watermark_utc is not None:
        context.set_iteration_fact('kpi_committed_watermark_utc', result.watermark_utc)
        context.set_execution_fact('kpi_committed_watermark_utc', result.watermark_utc)
    if result.delivery_revision is not None:
        context.set_iteration_fact('delivery_revision', result.delivery_revision)
        context.set_execution_fact('delivery_revision', result.delivery_revision)
    context.set_iteration_fact('destination_count', result.destination_count)
    context.set_iteration_fact('value_count', result.value_count)
    context.set_iteration_fact('missing_count', result.missing_count)
    context.set_iteration_fact('error_count', result.error_count)
    if outcome == 'completed':
        context.mark_iteration_work()
        if result.status is KpiLatestDeliveryIterationStatus.PUBLISHED:
            context.increment_execution_counter('snapshots_published')
    return result


# Mantiene aislada la responsabilidad de _utc_now.
def _utc_now() -> datetime:
    return datetime.now(UTC)
