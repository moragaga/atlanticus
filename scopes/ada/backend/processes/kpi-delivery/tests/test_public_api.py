from __future__ import annotations

import ada.processes.kpi_delivery as package


def test_public_api_and_version() -> None:
    assert package.__version__ == '1.0.0'
    assert package.KpiLatestDeliveryJob is not None
    assert package.KpiDeliveryComposition is not None
    assert package.KpiLatestSnapshotRepository is not None
