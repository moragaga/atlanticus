import pytest

from ada.kpis.materialization import (
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from ada.processes.kpi_materialization.errors import (
    KpiMaterializationIterationError,
)
from ada.processes.kpi_materialization.job import (
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
    return LocalKpiRegistryStore(root=materialization_root(tmp_path.resolve()))


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


def test_pending_registry_retries_after_readiness_interval_without_failing_other_tools(tmp_path):
    store = _store(tmp_path)
    context = Context()
    job = KpiMaterializationJob(
        repositories={
            'tool_a': Reader(projection(revision='new-a')),
            'tool_b': Reader(error=pending_error()),
        },
        store=store,
    )

    result = job.run_iteration(context)

    assert result.updated_tools == 1
    assert result.pending_tools == 1
    assert context.facts['failed_tools'] == 0
    assert context.next_delay == READINESS_RETRY_SECONDS
    assert store.read('tool_a')['source_release_id'] == 'new-a'
    assert store.read('tool_b') is None


def test_failed_tool_keeps_previous_authority_and_does_not_block_other_updates(tmp_path):
    store = _store(tmp_path)
    old = materialize_registry(
        tool_key='tool_b',
        projection=projection(revision='old', tool_key='tool_b'),
    )
    store.replace(tool_key='tool_b', document=old)
    job = KpiMaterializationJob(
        repositories={
            'tool_a': Reader(projection(revision='new-a')),
            'tool_b': Reader(error=acquisition_error()),
        },
        store=store,
    )
    context = Context()

    with pytest.raises(KpiMaterializationIterationError, match='tool_b'):
        job.run_iteration(context)

    assert store.read('tool_a')['source_release_id'] == 'new-a'
    assert store.read('tool_b') == old
    assert context.facts['failed_tools'] == 1


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
