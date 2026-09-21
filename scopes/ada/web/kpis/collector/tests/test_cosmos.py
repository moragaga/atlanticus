from __future__ import annotations

import pytest

from ada.web.kpis.collector import CosmosKpiDeliveryReader, KpiDeliveryReadError
from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError


class MissingContainerClient:
    def find_item(self, **_kwargs):
        raise CosmosContainerNotFoundError('Cosmos container was not found')


def test_missing_delivery_container_is_reported_as_degradable_read_failure() -> None:
    reader = CosmosKpiDeliveryReader(MissingContainerClient())

    with pytest.raises(
        KpiDeliveryReadError,
        match='Could not read KPI delivery from Cosmos',
    ) as exc:
        reader.read_latest()

    assert isinstance(exc.value.__cause__, CosmosContainerNotFoundError)
