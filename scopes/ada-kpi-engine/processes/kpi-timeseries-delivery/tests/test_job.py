from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
    KpiTimeseriesDeliveryPublicationError,
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.job import KpiTimeseriesDeliveryJob
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesDeliveryIterationStatus,
)
from ada.processes.kpi_timeseries_delivery.planning import (
    build_timeseries_read_plan,
)
from tests.support import (
    AuthorityReader,
    CheckpointStore,
    ParallelPublisherStub,
    RollingReader,
    RuntimeContextStub,
    SnapshotPublisher,
    authority,
    checkpoint,
    frozen,
    histories,
)

NOW = datetime(2026, 9, 1, 5, 4, 1, tzinfo=UTC)


def _job(*, configurations, checkpoints=None, publishers=None, source=None):
    resolved_publishers = (
        {key: SnapshotPublisher(key) for key in configurations}
        if publishers is None
        else publishers
    )
    rolling = RollingReader(histories() if source is None else source)
    store = CheckpointStore(checkpoints)
    publisher = ParallelPublisherStub(resolved_publishers)
    return (
        KpiTimeseriesDeliveryJob(
            configurations=configurations,
            read_plan=build_timeseries_read_plan(configurations),
            historian=AuthorityReader(authority(4)),
            rolling=rolling,
            checkpoints=store,
            publisher=publisher,
            now=lambda: NOW,
        ),
        rolling,
        store,
        resolved_publishers,
        publisher,
    )


def test_current_tools_skip_before_rolling_read():
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64),
        'tool_b': frozen('tool_b', digest='b' * 64),
    }
    job, rolling, _, publishers, publisher = _job(
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(4, digest='a' * 64),
            'tool_b': checkpoint(4, digest='b' * 64),
        },
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiTimeseriesDeliveryIterationStatus.SKIPPED_CURRENT
    assert rolling.calls == []
    assert publisher.calls == 0
    assert all(item.snapshots == [] for item in publishers.values())


def test_pending_tools_share_one_consolidated_rolling_read():
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64, key='produccion_total', hours=1),
        'tool_b': frozen('tool_b', digest='b' * 64, key='otra', hours=6),
    }
    job, rolling, store, publishers, publisher = _job(
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(2, digest='a' * 64),
            'tool_b': checkpoint(2, digest='b' * 64),
        },
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiTimeseriesDeliveryIterationStatus.PUBLISHED
    assert len(rolling.calls) == 1
    assert rolling.calls[0]['keys'] == ('otra', 'produccion_total')
    assert rolling.calls[0]['start_utc'] == datetime(2026, 8, 31, 23, 4, tzinfo=UTC)
    assert tuple(task.tool_key for task in publisher.tasks[0]) == ('tool_a', 'tool_b')
    assert publishers['tool_a'].snapshots[0].step_seconds == 120
    assert publishers['tool_b'].snapshots[0].manifest.schema_version == 2
    assert store.values['tool_a'].watermark == checkpoint(4).watermark
    assert store.values['tool_b'].watermark == checkpoint(4).watermark
    assert context.lease_checks == 2
    assert context.fences == 2


def test_partial_failure_preserves_successful_tool_progress():
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64),
        'tool_b': frozen('tool_b', digest='b' * 64),
        'tool_c': frozen('tool_c', digest='c' * 64),
    }
    publishers = {key: SnapshotPublisher(key) for key in configurations}
    publishers['tool_b'].error = KpiTimeseriesDeliveryRepositoryError('cosmos unavailable')
    job, rolling, store, _, publisher = _job(
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(2, digest='a' * 64),
            'tool_b': checkpoint(2, digest='b' * 64),
            'tool_c': checkpoint(2, digest='c' * 64),
        },
        publishers=publishers,
    )

    with pytest.raises(KpiTimeseriesDeliveryPublicationError, match='tool_b'):
        job.run_iteration(RuntimeContextStub())

    assert store.values['tool_a'].watermark == checkpoint(4).watermark
    assert store.values['tool_b'].watermark == checkpoint(2).watermark
    assert store.values['tool_c'].watermark == checkpoint(4).watermark
    assert len(rolling.calls) == 1

    publishers['tool_b'].error = None
    result = job.run_iteration(RuntimeContextStub())

    assert result.pending_tool_count == 1
    assert tuple(task.tool_key for task in publisher.tasks[1]) == ('tool_b',)
    assert store.values['tool_b'].watermark == checkpoint(4).watermark
    assert len(rolling.calls) == 2


def test_same_registry_revision_with_different_digest_is_integrity_error():
    configurations = {
        'tool_a': frozen('tool_a', revision='r1', digest='b' * 64),
    }
    job, rolling, _, _, publisher = _job(
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(4, revision='r1', digest='a' * 64),
        },
    )

    with pytest.raises(
        KpiTimeseriesDeliveryConfigurationError,
        match='without a new revision',
    ):
        job.run_iteration(RuntimeContextStub())

    assert rolling.calls == []
    assert publisher.calls == 0


def test_historian_watermark_cannot_regress_behind_tool_checkpoint():
    configurations = {'tool_a': frozen('tool_a', digest='a' * 64)}
    job, _, _, _, _ = _job(
        configurations=configurations,
        checkpoints={'tool_a': checkpoint(6, digest='a' * 64)},
    )

    with pytest.raises(KpiTimeseriesDeliveryRepositoryError, match='regressed'):
        job.run_iteration(RuntimeContextStub())
