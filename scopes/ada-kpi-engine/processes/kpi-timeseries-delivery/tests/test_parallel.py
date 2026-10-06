from __future__ import annotations

import threading
from datetime import UTC, datetime

from ada.kpis.delivery import project_kpi_timeseries
from ada.processes.kpi_timeseries_delivery.models import (
    KpiTimeseriesPublicationStatus,
)
from ada.processes.kpi_timeseries_delivery.parallel import (
    KpiTimeseriesPublicationTask,
    ParallelKpiTimeseriesPublisher,
)

from .support import SnapshotPublisher, configuration


class BarrierPublisher(SnapshotPublisher):
    def __init__(self, tool_key, barrier):
        super().__init__(tool_key)
        self.barrier = barrier
        self.thread_name = None

    def publish(self, snapshot):
        self.thread_name = threading.current_thread().name
        self.barrier.wait(timeout=2)
        return super().publish(snapshot)


def _snapshot():
    return project_kpi_timeseries(
        configuration=configuration(),
        histories={},
        historian_revision='h1',
        end_utc=datetime(2026, 9, 1, 5, 4, tzinfo=UTC),
        published_at_utc=datetime(2026, 9, 1, 5, 4, 1, tzinfo=UTC),
    )


def test_parallel_publisher_executes_tools_concurrently():
    barrier = threading.Barrier(2)
    publishers = {
        'tool_a': BarrierPublisher('tool_a', barrier),
        'tool_b': BarrierPublisher('tool_b', barrier),
    }
    parallel = ParallelKpiTimeseriesPublisher(
        publishers=publishers,
        max_workers=2,
    )
    try:
        results = parallel.publish(
            (
                KpiTimeseriesPublicationTask('tool_a', _snapshot()),
                KpiTimeseriesPublicationTask('tool_b', _snapshot()),
            )
        )
    finally:
        parallel.close()

    assert all(result.successful for result in results)
    assert publishers['tool_a'].thread_name.startswith('kpi-timeseries')
    assert publishers['tool_b'].thread_name.startswith('kpi-timeseries')
    assert publishers['tool_a'].thread_name != publishers['tool_b'].thread_name


def test_parallel_publisher_isolates_tool_failure():
    ok = SnapshotPublisher('tool_a')
    failed = SnapshotPublisher('tool_b')
    failed.error = RuntimeError('boom')
    parallel = ParallelKpiTimeseriesPublisher(
        publishers={'tool_a': ok, 'tool_b': failed},
        max_workers=2,
    )
    try:
        results = parallel.publish(
            (
                KpiTimeseriesPublicationTask('tool_a', _snapshot()),
                KpiTimeseriesPublicationTask('tool_b', _snapshot()),
            )
        )
    finally:
        parallel.close()

    by_tool = {result.tool_key: result for result in results}
    assert by_tool['tool_a'].publication.status is KpiTimeseriesPublicationStatus.PUBLISHED
    assert by_tool['tool_b'].error is not None
