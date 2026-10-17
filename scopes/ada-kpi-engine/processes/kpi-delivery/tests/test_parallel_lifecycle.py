from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from ada.processes.kpi_delivery.composition import build_composition
from ada.processes.kpi_delivery.job import KpiLatestDeliveryJob
from ada.processes.kpi_delivery.models import (
    KpiLatestPublication,
    KpiLatestPublicationStatus,
)
from ada.processes.kpi_delivery.parallel import (
    KpiLatestPublicationTask,
    ParallelKpiLatestPublisher,
)
from ada.processes.kpi_delivery.repository import KpiLatestSnapshotRepository
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.runtime import LeaseOwnershipLostError

from .support import (
    CheckpointStore,
    CommitStateReader,
    EvaluationReader,
    RuntimeContextStub,
    SnapshotPublisher,
    batch,
    evaluation,
    frozen,
    watermark,
)
from .test_composition import _configuration
from .test_parallel import _snapshot


@pytest.mark.parametrize('cancel_during_publication', [False, True])
def test_parallel_work_drains_under_lease_before_clients_close(
    tmp_path, monkeypatch, cancel_during_publication
):
    composition = build_composition(
        configuration=_configuration(tmp_path),
        connections={
            'tool_a': CosmosSettings(
                endpoint='http://localhost:8081',
                database_name='tool-a',
                key='local-key',
                allow_insecure_http=True,
            ),
        },
    )
    lease = tmp_path / 'ada-kpi-delivery-local' / '.runtime' / 'leases' / 'kpi-delivery.json'
    started = Event()
    release = Event()
    events = []
    outcomes = []
    contexts = []
    pool = composition.parallel_publisher
    client = composition.clients['tool_a']
    original_pool_close = pool.close
    original_client_close = client.close

    def publish_snapshot(self, snapshot):
        assert lease.exists()
        events.append('worker_started')
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError('Controlled publication was not released')
        events.append('worker_finished')
        return KpiLatestPublication(
            status=KpiLatestPublicationStatus.PUBLISHED,
            revision=snapshot.manifest.revision,
        )

    def close_pool():
        assert lease.exists()
        events.append('pool_closed')
        original_pool_close()

    def close_client():
        assert lease.exists()
        events.append('client_closed')
        original_client_close()

    def iteration(context):
        contexts.append(context)
        context.assert_lease_current()
        pool.publish((KpiLatestPublicationTask('tool_a', _snapshot()),))
        context.raise_if_cancelled()

    def execute():
        try:
            outcomes.append(composition.execute(argv=('--run-once',)))
        except BaseException as error:
            outcomes.append(error)

    monkeypatch.setattr(KpiLatestSnapshotRepository, 'publish', publish_snapshot)
    monkeypatch.setattr(pool, 'close', close_pool)
    monkeypatch.setattr(client, 'close', close_client)
    composition.job = SimpleNamespace(run_iteration=iteration)
    thread = Thread(target=execute, daemon=True)
    thread.start()
    try:
        assert started.wait(timeout=5)
        assert lease.exists()
        assert thread.is_alive()
        assert events == ['worker_started']
        if cancel_during_publication:
            contexts[0].request_stop('requested')
            assert lease.exists()
            assert events == ['worker_started']
    finally:
        release.set()
        thread.join(timeout=8)

    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert not isinstance(outcomes[0], BaseException)
    assert outcomes[0].stop_reason == (
        'requested' if cancel_during_publication else 'run_once'
    )
    assert events == ['worker_started', 'worker_finished', 'pool_closed', 'client_closed']
    assert not lease.exists()


def test_authority_loss_after_dispatch_blocks_checkpoint_but_not_inflight_publication():
    entered = Event()
    release = Event()
    authority_lost = Event()
    remote_write = Event()
    outcomes = []
    store = CheckpointStore()
    committed = watermark(10)

    class RevocableContext(RuntimeContextStub):
        def assert_lease_current(self):
            super().assert_lease_current()
            if authority_lost.is_set():
                raise LeaseOwnershipLostError('Lease authority was lost')

    class ControlledPublisher(SnapshotPublisher):
        def publish(self, snapshot):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError('Controlled publication was not released')
            remote_write.set()
            return super().publish(snapshot)

    parallel = ParallelKpiLatestPublisher(
        publishers={'tool_a': ControlledPublisher('tool_a')},
        max_workers=1,
    )
    job = KpiLatestDeliveryJob(
        configurations={'tool_a': frozen('tool_a', digest='a' * 64)},
        kpi_state=CommitStateReader(committed),
        evaluations=EvaluationReader(
            batch(evaluation('produccion_total', watermark_value=committed))
        ),
        checkpoints=store,
        publisher=parallel,
        now=lambda: datetime(2026, 9, 1, 5, 10, 1, tzinfo=UTC),
    )
    context = RevocableContext()

    def execute():
        try:
            outcomes.append(job.run_iteration(context))
        except BaseException as error:
            outcomes.append(error)

    thread = Thread(target=execute, daemon=True)
    thread.start()
    try:
        assert entered.wait(timeout=5)
        authority_lost.set()
    finally:
        release.set()
        thread.join(timeout=8)
        parallel.close()

    assert not thread.is_alive()
    assert remote_write.is_set()
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], LeaseOwnershipLostError)
    assert context.lease_checks == 2
    assert store.commit_calls == []
    assert store.values == {}
