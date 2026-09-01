from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.job import KpiLatestDeliveryJob
from ada.processes.kpi_delivery.models import (
    KpiDeliveryCheckpoint,
    KpiLatestDeliveryIterationStatus,
    KpiLatestPublicationStatus,
)
from tests.support import (
    CheckpointStore,
    CommitStateReader,
    EvaluationReader,
    RuntimeContextStub,
    SnapshotPublisher,
    batch,
    configuration,
    evaluation,
    watermark,
)

NOW = datetime(2026, 9, 1, 5, 0, 1, tzinfo=UTC)


def _job(
    *,
    config=None,
    committed=None,
    source_batch=None,
    checkpoint=None,
    publisher=None,
    events=None,
):
    return KpiLatestDeliveryJob(
        configuration=configuration() if config is None else config,
        kpi_state=CommitStateReader(committed),
        evaluations=EvaluationReader(source_batch),
        checkpoint=CheckpointStore(checkpoint, events=events),
        snapshots=SnapshotPublisher(events=events) if publisher is None else publisher,
        now=lambda: NOW,
    )


def test_missing_committed_watermark_is_empty_without_publication() -> None:
    context = RuntimeContextStub()
    publisher = SnapshotPublisher()
    job = KpiLatestDeliveryJob(
        configuration=configuration(),
        kpi_state=CommitStateReader(None),
        evaluations=EvaluationReader(None),
        checkpoint=CheckpointStore(),
        snapshots=publisher,
        now=lambda: NOW,
    )

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING
    assert context.iteration_facts['outcome'] == 'empty'
    assert publisher.calls == 0
    assert not context.work


def test_current_checkpoint_skips_before_evaluation_read() -> None:
    current = watermark()
    reader = EvaluationReader(batch(evaluation('produccion_total')))
    job = KpiLatestDeliveryJob(
        configuration=configuration(),
        kpi_state=CommitStateReader(current),
        evaluations=reader,
        checkpoint=CheckpointStore(KpiDeliveryCheckpoint(current, 'config-r1')),
        snapshots=SnapshotPublisher(),
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.SKIPPED_CURRENT
    assert reader.calls == 0
    assert context.iteration_facts['outcome'] == 'skipped'
    assert not context.work


def test_configuration_revision_change_republishes_same_watermark() -> None:
    current = watermark()
    source = batch(evaluation('produccion_total', watermark_value=current))
    events: list[str] = []
    checkpoint_store = CheckpointStore(KpiDeliveryCheckpoint(current, 'config-r1'), events=events)
    publisher = SnapshotPublisher(events=events)
    job = KpiLatestDeliveryJob(
        configuration=configuration('config-r2'),
        kpi_state=CommitStateReader(current),
        evaluations=EvaluationReader(source),
        checkpoint=checkpoint_store,
        snapshots=publisher,
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.PUBLISHED
    assert events == ['publish', 'checkpoint']
    assert checkpoint_store.value == KpiDeliveryCheckpoint(current, 'config-r2')
    assert context.lease_checks == 2
    assert context.fences == 1


def test_publish_happens_before_checkpoint_and_missing_is_projected() -> None:
    current = watermark()
    source = batch(evaluation('otra', watermark_value=current))
    events: list[str] = []
    checkpoint_store = CheckpointStore(events=events)
    publisher = SnapshotPublisher(events=events)
    job = KpiLatestDeliveryJob(
        configuration=configuration(),
        kpi_state=CommitStateReader(current),
        evaluations=EvaluationReader(source),
        checkpoint=checkpoint_store,
        snapshots=publisher,
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.PUBLISHED
    assert result.missing_count == 1
    assert events == ['publish', 'checkpoint']
    assert context.work
    assert context.execution_counters['snapshots_published'] == 1


def test_unchanged_publication_still_commits_checkpoint() -> None:
    current = watermark()
    source = batch(evaluation('produccion_total', watermark_value=current))
    publisher = SnapshotPublisher(status=KpiLatestPublicationStatus.UNCHANGED)
    checkpoint_store = CheckpointStore()
    job = KpiLatestDeliveryJob(
        configuration=configuration(),
        kpi_state=CommitStateReader(current),
        evaluations=EvaluationReader(source),
        checkpoint=checkpoint_store,
        snapshots=publisher,
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.UNCHANGED
    assert checkpoint_store.commit_calls == 1
    assert context.work
    assert 'snapshots_published' not in context.execution_counters


def test_publication_failure_does_not_commit_checkpoint() -> None:
    current = watermark()
    source = batch(evaluation('produccion_total', watermark_value=current))
    publisher = SnapshotPublisher()
    publisher.error = RuntimeError('publish failed')
    checkpoint_store = CheckpointStore()
    job = KpiLatestDeliveryJob(
        configuration=configuration(),
        kpi_state=CommitStateReader(current),
        evaluations=EvaluationReader(source),
        checkpoint=checkpoint_store,
        snapshots=publisher,
        now=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match='publish failed'):
        job.run_iteration(RuntimeContextStub())

    assert checkpoint_store.commit_calls == 0


def test_missing_batch_for_committed_watermark_fails() -> None:
    current = watermark()
    job = _job(committed=current, source_batch=None)

    with pytest.raises(KpiDeliveryRepositoryError, match='batch is missing'):
        job.run_iteration(RuntimeContextStub())


def test_committed_watermark_must_not_regress() -> None:
    job = _job(
        committed=watermark(1),
        checkpoint=KpiDeliveryCheckpoint(watermark(2), 'config-r1'),
    )

    with pytest.raises(KpiDeliveryRepositoryError, match='must not regress'):
        job.run_iteration(RuntimeContextStub())
