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



def test_delivery_container_failure_has_distinct_exception() -> None:
    from ada.web.kpis.collector import KpiDeliveryContainerMissingError

    reader = CosmosKpiDeliveryReader(MissingContainerClient())
    with pytest.raises(KpiDeliveryContainerMissingError):
        reader.read_timeseries()


def test_missing_kpi_document_does_not_raise() -> None:
    class Empty:
        def find_item(self, **kwargs):
            return None

    reader = CosmosKpiDeliveryReader(Empty())
    assert reader.read_latest() is None


def test_ambiguous_kpi_404_checks_missing_container(monkeypatch) -> None:
    from ada.web.kpis.collector import cosmos as module
    from ada.web.kpis.collector import KpiDeliveryContainerMissingError
    from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError

    class Empty:
        def find_item(self, **kwargs):
            return None

    class Inventory:
        def __init__(self, *, client):
            pass

        def read_container(self, *, container_name):
            raise CosmosContainerNotFoundError('container not found')

    monkeypatch.setattr(module, 'CosmosClient', Empty)
    monkeypatch.setattr(module, 'CosmosInventory', Inventory)
    reader = CosmosKpiDeliveryReader(Empty())
    with pytest.raises(KpiDeliveryContainerMissingError):
        reader.read_latest()
