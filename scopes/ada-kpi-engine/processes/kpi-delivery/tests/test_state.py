import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiDeliveryCheckpoint
from ada.processes.kpi_delivery.state import KpiLatestDeliveryCheckpointStore
from atlanticus.state import AtomicStateStore
from tests.support import watermark


def test_checkpoint_is_independent_per_tool(tmp_path):
    store = KpiLatestDeliveryCheckpointStore(
        store=AtomicStateStore(
            volume_path=tmp_path,
            application='ada-kpi-delivery-test',
        )
    )
    a = KpiDeliveryCheckpoint(watermark(1), 'r1', 'a' * 64)
    b = KpiDeliveryCheckpoint(watermark(2), 'r2', 'b' * 64)

    store.commit('tool_a', a)
    store.commit('tool_b', b)

    assert store.read('tool_a') == a
    assert store.read('tool_b') == b


def test_checkpoint_rejects_watermark_regression_per_tool(tmp_path):
    store = KpiLatestDeliveryCheckpointStore(
        store=AtomicStateStore(
            volume_path=tmp_path,
            application='ada-kpi-delivery-test',
        )
    )
    store.commit(
        'tool_a',
        KpiDeliveryCheckpoint(watermark(2), 'r1', 'a' * 64),
    )

    with pytest.raises(KpiDeliveryRepositoryError, match='must not regress'):
        store.commit(
            'tool_a',
            KpiDeliveryCheckpoint(watermark(1), 'r1', 'a' * 64),
        )
