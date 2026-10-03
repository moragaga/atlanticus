from datetime import UTC, datetime

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesCheckpoint
from ada.processes.kpi_timeseries_delivery.state import (
    KpiTimeseriesDeliveryCheckpointStore,
)
from atlanticus.state import AtomicStateStore


def test_checkpoints_are_isolated_per_tool(tmp_path):
    store = KpiTimeseriesDeliveryCheckpointStore(
        store=AtomicStateStore(
            volume_path=tmp_path,
            application='timeseries-test',
        )
    )
    first = KpiTimeseriesCheckpoint(
        watermark=KpiWatermark(datetime(2026, 9, 1, 5, 4, tzinfo=UTC)),
        registry_revision='r1',
        registry_digest='a' * 64,
    )
    second = KpiTimeseriesCheckpoint(
        watermark=KpiWatermark(datetime(2026, 9, 1, 5, 6, tzinfo=UTC)),
        registry_revision='r2',
        registry_digest='b' * 64,
    )

    store.commit('tool_a', first)
    store.commit('tool_b', second)

    assert store.read('tool_a') == first
    assert store.read('tool_b') == second
