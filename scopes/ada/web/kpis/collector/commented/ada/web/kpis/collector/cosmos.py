from __future__ import annotations

# Este adaptador es sólo lectura: conoce las direcciones físicas de los dos documentos y traduce
# fallos Cosmos a un error del collector.
# La ausencia del contenedor no aprovisiona infraestructura ni rompe el bootstrap; el runtime
# captura el fallo y vuelve a intentar.
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ada.web.kpis.collector.contracts import (
    KPI_DELIVERY_PARTITION_ID,
    KPI_LATEST_DELIVERY_ITEM_ID,
    KPI_TIMESERIES_DELIVERY_ITEM_ID,
)
from ada.web.kpis.collector.models import KpiDeliveryReadError
from atlanticus.connectivity.cosmos import CosmosError


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
            return self.client.find_item(
                container_name=container_name,
                item_id=item_id,
                partition_key=KPI_DELIVERY_PARTITION_ID,
            )
        except CosmosError as error:
            raise KpiDeliveryReadError('Could not read KPI delivery from Cosmos') from error
