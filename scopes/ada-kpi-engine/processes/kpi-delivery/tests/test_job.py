from datetime import UTC, datetime

import pytest

from ada.processes.kpi_delivery.errors import (
    KpiDeliveryConfigurationError,
    KpiDeliveryPublicationError,
    KpiDeliveryRepositoryError,
)
from ada.processes.kpi_delivery.job import KpiLatestDeliveryJob
from ada.processes.kpi_delivery.models import KpiLatestDeliveryIterationStatus
from tests.support import (
    CheckpointStore,
    CommitStateReader,
    EvaluationReader,
    ParallelPublisherStub,
    RuntimeContextStub,
    SnapshotPublisher,
    batch,
    checkpoint,
    evaluation,
    frozen,
    watermark,
)

NOW = datetime(2026, 9, 1, 5, 10, 1, tzinfo=UTC)


def _job(*, current, configurations, checkpoints=None, publishers=None):
    source = (
        None
        if current is None
        else batch(
            evaluation('produccion_total', watermark_value=current),
            evaluation('otra', watermark_value=current),
        )
    )
    resolved_publishers = (
        {key: SnapshotPublisher(key) for key in configurations}
        if publishers is None
        else publishers
    )
    reader = EvaluationReader(source)
    store = CheckpointStore(checkpoints)
    publisher = ParallelPublisherStub(resolved_publishers)
    return (
        KpiLatestDeliveryJob(
            configurations=configurations,
            kpi_state=CommitStateReader(current),
            evaluations=reader,
            checkpoints=store,
            publisher=publisher,
            now=lambda: NOW,
        ),
        reader,
        store,
        resolved_publishers,
        publisher,
    )


def test_missing_runtime_watermark_does_not_read_batch_or_publish():
    configurations = {'tool_a': frozen('tool_a', digest='a' * 64)}
    job, reader, _, publishers, publisher = _job(
        current=None,
        configurations=configurations,
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING
    assert reader.calls == 0
    assert publisher.calls == 0
    assert publishers['tool_a'].calls == 0


def test_current_tools_skip_without_reading_batch():
    current = watermark(10)
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64),
        'tool_b': frozen('tool_b', digest='b' * 64),
    }
    job, reader, _, publishers, publisher = _job(
        current=current,
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(10, digest='a' * 64),
            'tool_b': checkpoint(10, digest='b' * 64),
        },
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiLatestDeliveryIterationStatus.SKIPPED_CURRENT
    assert reader.calls == 0
    assert publisher.calls == 0
    assert all(item.calls == 0 for item in publishers.values())


def test_new_global_watermark_reads_batch_once_and_builds_all_publications_together():
    current = watermark(10)
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64),
        'tool_b': frozen('tool_b', digest='b' * 64),
    }
    job, reader, store, publishers, publisher = _job(
        current=current,
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(5, digest='a' * 64),
            'tool_b': checkpoint(5, digest='b' * 64),
        },
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiLatestDeliveryIterationStatus.PUBLISHED
    assert reader.calls == 1
    assert publisher.calls == 1
    assert tuple(task.tool_key for task in publisher.tasks[0]) == ('tool_a', 'tool_b')
    published_times = {item.snapshots[0].manifest.published_at_utc for item in publishers.values()}
    assert published_times == {'2026-09-01T05:10:01Z'}
    assert {value.watermark for value in store.values.values()} == {current}
    assert context.lease_checks == 2
    assert context.fences == 2


def test_registry_change_republishes_only_changed_tool_at_same_watermark():
    current = watermark(10)
    configurations = {
        'tool_a': frozen('tool_a', revision='r1', digest='a' * 64),
        'tool_b': frozen('tool_b', revision='r2', digest='b' * 64),
    }
    job, reader, store, publishers, publisher = _job(
        current=current,
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(10, revision='r1', digest='a' * 64),
            'tool_b': checkpoint(10, revision='r1', digest='c' * 64),
        },
    )

    result = job.run_iteration(RuntimeContextStub())

    assert reader.calls == 1
    assert publisher.calls == 1
    assert tuple(task.tool_key for task in publisher.tasks[0]) == ('tool_b',)
    assert publishers['tool_a'].calls == 0
    assert publishers['tool_b'].calls == 1
    assert store.values['tool_b'].registry_revision == 'r2'
    assert result.pending_tool_count == 1


def test_partial_failure_advances_successful_tools_and_retries_only_failed_tool():
    current = watermark(10)
    configurations = {
        'tool_a': frozen('tool_a', digest='a' * 64),
        'tool_b': frozen('tool_b', digest='b' * 64),
        'tool_c': frozen('tool_c', digest='c' * 64),
    }
    publishers = {key: SnapshotPublisher(key) for key in configurations}
    publishers['tool_b'].error = KpiDeliveryRepositoryError('cosmos unavailable')
    job, reader, store, _, publisher = _job(
        current=current,
        configurations=configurations,
        checkpoints={
            key: checkpoint(5, digest=digest * 64)
            for key, digest in (('tool_a', 'a'), ('tool_b', 'b'), ('tool_c', 'c'))
        },
        publishers=publishers,
    )

    with pytest.raises(KpiDeliveryPublicationError, match='tool_b'):
        job.run_iteration(RuntimeContextStub())

    assert store.values['tool_a'].watermark == current
    assert store.values['tool_b'].watermark == watermark(5)
    assert store.values['tool_c'].watermark == current
    assert reader.calls == 1

    publishers['tool_b'].error = None
    result = job.run_iteration(RuntimeContextStub())

    assert result.pending_tool_count == 1
    assert tuple(task.tool_key for task in publisher.tasks[1]) == ('tool_b',)
    assert publishers['tool_a'].calls == 1
    assert publishers['tool_b'].calls == 2
    assert publishers['tool_c'].calls == 1
    assert reader.calls == 2
    assert store.values['tool_b'].watermark == current


def test_same_registry_revision_with_different_digest_is_integrity_error():
    current = watermark(10)
    configurations = {
        'tool_a': frozen('tool_a', revision='r1', digest='b' * 64),
    }
    job, reader, _, _, publisher = _job(
        current=current,
        configurations=configurations,
        checkpoints={
            'tool_a': checkpoint(10, revision='r1', digest='a' * 64),
        },
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='without a new revision'):
        job.run_iteration(RuntimeContextStub())

    assert reader.calls == 0
    assert publisher.calls == 0


def test_runtime_watermark_cannot_regress_behind_any_tool_checkpoint():
    configurations = {'tool_a': frozen('tool_a', digest='a' * 64)}
    job, _, _, _, _ = _job(
        current=watermark(5),
        configurations=configurations,
        checkpoints={'tool_a': checkpoint(10, digest='a' * 64)},
    )

    with pytest.raises(KpiDeliveryRepositoryError, match='regressed'):
        job.run_iteration(RuntimeContextStub())
