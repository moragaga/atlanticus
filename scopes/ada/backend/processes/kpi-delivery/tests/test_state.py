from __future__ import annotations

import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import KpiDeliveryCheckpoint
from ada.processes.kpi_delivery.state import KpiLatestDeliveryCheckpointStore
from atlanticus.state import AtomicStateStore
from tests.support import watermark


def test_checkpoint_round_trip_and_idempotence(tmp_path) -> None:
    store = KpiLatestDeliveryCheckpointStore(
        store=AtomicStateStore(volume_path=tmp_path, application='ada-kpi-delivery-test')
    )
    checkpoint = KpiDeliveryCheckpoint(watermark(), 'config-r1')

    assert store.read() is None
    assert store.commit(checkpoint) == checkpoint
    assert store.read() == checkpoint
    assert store.commit(checkpoint) == checkpoint


def test_checkpoint_rejects_watermark_regression(tmp_path) -> None:
    store = KpiLatestDeliveryCheckpointStore(
        store=AtomicStateStore(volume_path=tmp_path, application='ada-kpi-delivery-test')
    )
    store.commit(KpiDeliveryCheckpoint(watermark(2), 'config-r1'))

    with pytest.raises(KpiDeliveryRepositoryError, match='must not regress'):
        store.commit(KpiDeliveryCheckpoint(watermark(1), 'config-r1'))
