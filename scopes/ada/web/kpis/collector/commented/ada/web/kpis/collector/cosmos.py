from __future__ import annotations

# Este adaptador es sólo lectura: conoce las direcciones físicas de los dos documentos y traduce
# fallos Cosmos a un error del collector.
# La ausencia del contenedor no aprovisiona infraestructura ni rompe el bootstrap; el runtime
# captura el fallo y vuelve a intentar.
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol

from ada.web.kpis.collector.contracts import (
    KPI_DELIVERY_PARTITION_ID,
    KPI_LATEST_DELIVERY_ITEM_ID,
    KPI_TIMESERIES_DELIVERY_ITEM_ID,
)
from ada.web.kpis.collector.models import (
    KpiDeliveryReadError, KpiDeliveryContainerMissingError,
)
from atlanticus.connectivity.cosmos import (
    CosmosClient, CosmosContainerNotFoundError, CosmosError, CosmosInventory,
)


def _validate_container_name(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')


DEFAULT_KPI_LATEST_DELIVERY_CONTAINER = 'ada-kpi-latest-delivery'
DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER = 'ada-kpi-timeseries-delivery'


class CosmosDocumentClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class CosmosKpiDeliveryReaderSettings:
    latest_container_name: str = DEFAULT_KPI_LATEST_DELIVERY_CONTAINER
    timeseries_container_name: str = DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER

    def __post_init__(self) -> None:
        _validate_container_name(self.latest_container_name, 'latest_container_name')
        _validate_container_name(self.timeseries_container_name, 'timeseries_container_name')


@dataclass(slots=True)
class CosmosKpiDeliveryReader:
    client: CosmosDocumentClient
    settings: CosmosKpiDeliveryReaderSettings = field(
        default_factory=CosmosKpiDeliveryReaderSettings
    )
    _inventory_cache: dict[str, tuple[float, bool]] = field(
        default_factory=dict, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        if not callable(getattr(self.client, 'find_item', None)):
            raise TypeError('client must provide a callable find_item method')
        if not isinstance(self.settings, CosmosKpiDeliveryReaderSettings):
            raise TypeError('settings must be CosmosKpiDeliveryReaderSettings')

    def read_latest(self) -> Mapping[str, Any] | None:
        return self._read(
            container_name=self.settings.latest_container_name,
            item_id=KPI_LATEST_DELIVERY_ITEM_ID,
        )

    def read_timeseries(self) -> Mapping[str, Any] | None:
        return self._read(
            container_name=self.settings.timeseries_container_name,
            item_id=KPI_TIMESERIES_DELIVERY_ITEM_ID,
        )

    def _read(self, *, container_name: str, item_id: str) -> Mapping[str, Any] | None:
        try:
            document = self.client.find_item(
                container_name=container_name,
                item_id=item_id,
                partition_key=KPI_DELIVERY_PARTITION_ID,
            )
        except CosmosContainerNotFoundError as error:
            raise KpiDeliveryContainerMissingError('Could not read KPI delivery from Cosmos: container missing') from error
        except CosmosError as error:
            raise KpiDeliveryReadError('Could not read KPI delivery from Cosmos') from error
        if document is None and self._container_missing(container_name):
            raise KpiDeliveryContainerMissingError('Could not read KPI delivery from Cosmos: container missing')
        return document

    def _container_missing(self, name: str) -> bool:
        if not isinstance(self.client, CosmosClient):
            return False
        now = monotonic()
        last = self._inventory_cache.get(name)
        # Verificacion de contenedor solo ante documento ausente, con cache por nombre.
        if last is not None and now - last[0] < 60.0:
            return last[1]
        try:
            CosmosInventory(client=self.client).read_container(container_name=name)
        except CosmosContainerNotFoundError:
            missing = True
        except CosmosError as error:
            raise KpiDeliveryReadError('Could not inspect KPI delivery container') from error
        else:
            missing = False
        self._inventory_cache[name] = (now, missing)
        return missing
