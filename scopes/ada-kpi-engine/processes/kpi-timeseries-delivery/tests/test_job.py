from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.job import KpiTimeseriesDeliveryJob
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesCheckpoint,
    KpiTimeseriesDeliveryIterationStatus,
)
from tests.support import (
    AuthorityReader,
    CheckpointStore,
    HistoryReader,
    RuntimeContextStub,
    SnapshotPublisher,
    authority,
    configuration,
    watermark,
)

NOW = datetime(2026, 9, 1, 5, 3, 30, tzinfo=UTC)


def test_missing_historian_authority_is_empty_without_publication() -> None:
    publisher = SnapshotPublisher()
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(None),
        history=HistoryReader(),
        checkpoint=CheckpointStore(),
        snapshots=publisher,
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiTimeseriesDeliveryIterationStatus.HISTORIAN_WATERMARK_MISSING
    assert publisher.calls == 0
    assert context.iteration_facts['outcome'] == 'empty'
    assert not context.work


def test_current_aligned_checkpoint_skips_before_history_read() -> None:
    history = HistoryReader()
    publisher = SnapshotPublisher()
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(authority(3)),
        history=history,
        checkpoint=CheckpointStore(
            KpiTimeseriesCheckpoint(
                watermark=watermark(2),
                configuration_revision='config-r1',
            )
        ),
        snapshots=publisher,
        now=lambda: NOW,
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT
    assert result.watermark_utc == '2026-09-01T05:02:00Z'
    assert history.calls == 0
    assert publisher.calls == 0


def test_new_historian_revision_inside_same_grid_does_not_republish() -> None:
    checkpoint = CheckpointStore(
        KpiTimeseriesCheckpoint(
            watermark=watermark(2),
            configuration_revision='config-r1',
        )
    )
    history = HistoryReader()
    publisher = SnapshotPublisher()
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(authority(3)),
        history=history,
        checkpoint=checkpoint,
        snapshots=publisher,
        now=lambda: NOW,
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT
    assert result.watermark_utc == '2026-09-01T05:02:00Z'
    assert history.calls == 0
    assert publisher.calls == 0
    assert checkpoint.commit_calls == 0
    assert checkpoint.value == KpiTimeseriesCheckpoint(
        watermark=watermark(2),
        configuration_revision='config-r1',
    )


def test_new_aligned_grid_publishes_and_advances_checkpoint() -> None:
    checkpoint = CheckpointStore(
        KpiTimeseriesCheckpoint(
            watermark=watermark(2),
            configuration_revision='config-r1',
        )
    )
    publisher = SnapshotPublisher()
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(authority(4)),
        history=HistoryReader(),
        checkpoint=checkpoint,
        snapshots=publisher,
        now=lambda: NOW,
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiTimeseriesDeliveryIterationStatus.PUBLISHED
    assert result.watermark_utc == '2026-09-01T05:04:00Z'
    assert publisher.calls == 1
    assert checkpoint.value == KpiTimeseriesCheckpoint(
        watermark=watermark(4),
        configuration_revision='config-r1',
    )


def test_configuration_change_republishes_same_aligned_watermark() -> None:
    events: list[str] = []
    checkpoint = CheckpointStore(
        KpiTimeseriesCheckpoint(
            watermark=watermark(2),
            configuration_revision='config-r1',
        ),
        events=events,
    )
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration('config-r2'),
        historian=AuthorityReader(authority(3)),
        history=HistoryReader(),
        checkpoint=checkpoint,
        snapshots=SnapshotPublisher(events=events),
        now=lambda: NOW,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiTimeseriesDeliveryIterationStatus.PUBLISHED
    assert events == ['publish', 'checkpoint']
    assert checkpoint.value == KpiTimeseriesCheckpoint(
        watermark=watermark(2),
        configuration_revision='config-r2',
    )
    assert context.lease_checks == 2
    assert context.fences == 1


def test_publish_failure_does_not_commit_checkpoint() -> None:
    publisher = SnapshotPublisher()
    publisher.error = RuntimeError('publish failed')
    checkpoint = CheckpointStore()
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(authority(3)),
        history=HistoryReader(),
        checkpoint=checkpoint,
        snapshots=publisher,
        now=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match='publish failed'):
        job.run_iteration(RuntimeContextStub())

    assert checkpoint.commit_calls == 0


def test_historian_watermark_must_not_regress() -> None:
    job = KpiTimeseriesDeliveryJob(
        configuration=configuration(),
        historian=AuthorityReader(authority(3)),
        history=HistoryReader(),
        checkpoint=CheckpointStore(
            KpiTimeseriesCheckpoint(
                watermark=watermark(4),
                configuration_revision='config-r1',
            )
        ),
        snapshots=SnapshotPublisher(),
        now=lambda: NOW,
    )

    with pytest.raises(KpiTimeseriesDeliveryRepositoryError, match='must not regress'):
        job.run_iteration(RuntimeContextStub())
