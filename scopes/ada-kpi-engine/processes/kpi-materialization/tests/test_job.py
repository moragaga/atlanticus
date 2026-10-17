import pytest

from ada.kpis.materialization import (
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from ada.processes.kpi_materialization.errors import KpiMaterializationIterationError
from ada.processes.kpi_materialization.job import (
    READINESS_MAX_ATTEMPTS,
    READINESS_RETRY_SECONDS,
    KpiMaterializationJob,
)

from .support import (
    Context,
    Reader,
    acquisition_error,
    pending_error,
    projection,
)


def _store(tmp_path):
    return LocalKpiRegistryStore(
        root=materialization_root(tmp_path.resolve(), application='materializer-a')
    )


class SequencedReader:
    def __init__(self, *values):
        self.values = values
        self.calls = 0

    def read(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value


def test_job_materializes_each_tool_independently(tmp_path):
    store = _store(tmp_path)
    context = Context()
    job = KpiMaterializationJob(
        repositories={
            'tool_a': Reader(projection(revision='r1')),
            'tool_b': Reader(projection(revision='r2', tool_key='tool_b')),
        },
        store=store,
    )

    result = job.run_iteration(context)

    assert result.configured_tools == 2
    assert result.updated_tools == 2
    assert result.unchanged_tools == 0
    assert result.removed_tools == 0
    assert result.pending_tools == 0
    assert store.read('tool_a')['tool_key'] == 'tool_a'
    assert store.read('tool_b')['source_release_id'] == 'r2'
    assert context.work == 2
    assert context.facts['failed_tools'] == 0
    assert context.waits == []


def test_pending_registry_retries_inside_one_iteration_without_failing_other_tools(tmp_path):
    store = _store(tmp_path)
    context = Context()
    ready = SequencedReader(projection(revision='new-a'))
    pending = SequencedReader(pending_error())
    job = KpiMaterializationJob(
        repositories={'tool_a': ready, 'tool_b': pending},
        store=store,
    )

    result = job.run_iteration(context)

    assert result.updated_tools == 1
    assert result.pending_tools == 1
    assert context.facts['failed_tools'] == 0
    assert context.facts['materialization_outcome'] == 'PENDING'
    assert context.next_delay is None
    assert context.waits == [READINESS_RETRY_SECONDS] * (READINESS_MAX_ATTEMPTS - 1)
    assert ready.calls == 1
    assert pending.calls == READINESS_MAX_ATTEMPTS
    assert store.read('tool_a')['source_release_id'] == 'new-a'
    assert store.read('tool_b') is None


def test_pending_tool_recovers_without_reprocessing_completed_tool(tmp_path):
    ready = SequencedReader(projection(revision='new-a'))
    retry = SequencedReader(
        pending_error(),
        pending_error(),
        projection(revision='new-b', tool_key='tool_b'),
    )
    job = KpiMaterializationJob(
        repositories={'tool_a': ready, 'tool_b': retry},
        store=_store(tmp_path),
        readiness_retry_seconds=0.5,
    )
    context = Context()

    result = job.run_iteration(context)

    assert result.updated_tools == 2
    assert result.pending_tools == 0
    assert context.facts['materialization_outcome'] == 'READY'
    assert ready.calls == 1
    assert retry.calls == 3
    assert context.waits == [0.5, 0.5]


def test_failed_tool_keeps_previous_authority_and_does_not_block_other_updates(tmp_path):
    store = _store(tmp_path)
    old = materialize_registry(
        tool_key='tool_b',
        projection=projection(revision='old', tool_key='tool_b'),
    )
    store.replace(tool_key='tool_b', document=old)
    failed = SequencedReader(acquisition_error())
    job = KpiMaterializationJob(
        repositories={
            'tool_a': Reader(projection(revision='new-a')),
            'tool_b': failed,
        },
        store=store,
    )
    context = Context()

    with pytest.raises(KpiMaterializationIterationError, match='tool_b'):
        job.run_iteration(context)

    assert store.read('tool_a')['source_release_id'] == 'new-a'
    assert store.read('tool_b') == old
    assert context.facts['failed_tools'] == 1
    assert failed.calls == 1
    assert context.waits == []


def test_job_prunes_registry_when_tool_is_removed_from_connections(tmp_path):
    store = _store(tmp_path)
    store.replace(
        tool_key='old_tool',
        document=materialize_registry(
            tool_key='old_tool',
            projection=projection(revision='old', tool_key='old_tool'),
        ),
    )
    job = KpiMaterializationJob(
        repositories={'tool_a': Reader()},
        store=store,
    )

    result = job.run_iteration(Context())

    assert result.removed_tools == 1
    assert store.read('old_tool') is None
    assert store.read('tool_a') is not None


def test_unchanged_registry_does_not_rewrite_authority(tmp_path):
    store = _store(tmp_path)
    document = materialize_registry(tool_key='tool_a', projection=projection())
    store.replace(tool_key='tool_a', document=document)
    context = Context()
    job = KpiMaterializationJob(
        repositories={'tool_a': Reader(projection())},
        store=store,
    )

    result = job.run_iteration(context)

    assert result.updated_tools == 0
    assert result.unchanged_tools == 1
    assert context.work == 0
    assert context.waits == []


def test_pending_wait_interruption_keeps_pending_without_extra_reads(tmp_path):
    reader = SequencedReader(pending_error())
    context = Context()
    context.wait_result = False
    job = KpiMaterializationJob(repositories={'tool_a': reader}, store=_store(tmp_path))

    result = job.run_iteration(context)

    assert result.pending_tools == 1
    assert reader.calls == 1
    assert context.waits == [READINESS_RETRY_SECONDS]


def test_cancelled_wait_aborts_before_final_mutation(tmp_path):
    class CancelContext(Context):
        def wait(self, seconds):
            self.cancelled = True
            return False

    reader = SequencedReader(pending_error())
    job = KpiMaterializationJob(repositories={'tool_a': reader}, store=_store(tmp_path))
    with pytest.raises(RuntimeError, match='cancelled'):
        job.run_iteration(CancelContext())


@pytest.mark.parametrize('value', (0, -1, True, float('inf'), float('nan')))
def test_readiness_retry_interval_must_be_positive_finite(tmp_path, value):
    with pytest.raises(ValueError, match='readiness_retry_seconds'):
        KpiMaterializationJob(
            repositories={'tool_a': Reader()},
            store=_store(tmp_path),
            readiness_retry_seconds=value,
        )
