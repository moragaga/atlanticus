from ada.kpis.materialization import (
    LocalKpiRegistryStore,
    materialization_root,
    materialize_registry,
)
from ada.processes.kpi_delivery.job import (
    READINESS_RETRY_SECONDS,
    KpiLatestDeliveryRuntimeJob,
)
from ada.processes.kpi_delivery.models import KpiLatestDeliveryIterationStatus
from tests.support import (
    CheckpointStore,
    CommitStateReader,
    EvaluationReader,
    ParallelPublisherStub,
    RuntimeContextStub,
    SnapshotPublisher,
)


def _projection():
    from ada.kpis.materialization import KPI_REGISTRY_ITEM_ID

    return {
        'id': KPI_REGISTRY_ITEM_ID,
        'partition_key': 'kpis',
        'document_type': 'ada_kpi_registry_projection_record',
        'schema_version': 1,
        'source_key': 'kpis',
        'source_release_id': 'registry-r1',
        'source_published_at_utc': '2026-10-02T12:00:00+00:00',
        'projected_at_utc': '2026-10-02T12:00:01+00:00',
        'dependencies': [
            {
                'source_key': 'tools',
                'source_release_id': 'tools-r1',
                'source_published_at_utc': '2026-10-02T11:59:00+00:00',
                'dependencies': [],
            }
        ],
        'payload': {
            'bindings': [
                {
                    'kpi_key': 'produccion_total',
                    'destination_keys': ['global_indicators'],
                    'latest_enabled': True,
                    'series_enabled': False,
                    'series_hours': None,
                }
            ]
        },
    }


def test_runtime_job_waits_for_materialization_then_freezes_it(tmp_path):
    store = LocalKpiRegistryStore(root=materialization_root(tmp_path.resolve()))
    publishers = {'tool_a': SnapshotPublisher('tool_a')}
    kpi_state = CommitStateReader(None)
    job = KpiLatestDeliveryRuntimeJob(
        store=store,
        expected_tool_keys=('tool_a',),
        kpi_state=kpi_state,
        evaluations=EvaluationReader(None),
        checkpoints=CheckpointStore(),
        publisher=ParallelPublisherStub(publishers),
    )
    waiting_context = RuntimeContextStub()

    waiting = job.run_iteration(waiting_context)

    assert waiting.status is KpiLatestDeliveryIterationStatus.MATERIALIZATION_PENDING
    assert waiting_context.next_delay == READINESS_RETRY_SECONDS
    assert waiting_context.iteration_facts['outcome'] == 'waiting'
    assert kpi_state.calls == 0

    store.replace(
        tool_key='tool_a',
        document=materialize_registry(
            tool_key='tool_a',
            projection=_projection(),
        ),
    )
    ready_context = RuntimeContextStub()

    ready = job.run_iteration(ready_context)

    assert ready.status is KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING
    assert kpi_state.calls == 1

    store.remove_unconfigured(())
    frozen_context = RuntimeContextStub()

    frozen = job.run_iteration(frozen_context)

    assert frozen.status is KpiLatestDeliveryIterationStatus.KPI_WATERMARK_MISSING
    assert frozen_context.next_delay is None
    assert kpi_state.calls == 2
