from __future__ import annotations

import pytest

from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_historian.errors import KpiHistorianRepositoryError
from ada.processes.kpi_historian.state import KpiHistorianAuthorityStore
from atlanticus.state import AtomicStateStore
from tests.support import watermark


def test_authority_round_trip_and_idempotence(tmp_path) -> None:
    store = KpiHistorianAuthorityStore(
        store=AtomicStateStore(volume_path=tmp_path, application='ada-kpi-historian-test')
    )
    authority = KpiHistorianAuthority(watermark().timestamp_utc)

    assert store.read() is None
    assert store.commit(authority) == authority
    assert store.read() == authority
    assert store.commit(authority) == authority


def test_authority_rejects_watermark_regression(tmp_path) -> None:
    store = KpiHistorianAuthorityStore(
        store=AtomicStateStore(volume_path=tmp_path, application='ada-kpi-historian-test')
    )
    store.commit(KpiHistorianAuthority(watermark(2).timestamp_utc))

    with pytest.raises(KpiHistorianRepositoryError, match='must not regress'):
        store.commit(KpiHistorianAuthority(watermark(1).timestamp_utc))
