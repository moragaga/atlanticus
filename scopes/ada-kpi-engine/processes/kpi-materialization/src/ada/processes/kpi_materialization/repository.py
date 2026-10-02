from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ada.kpis.materialization import (
    KPI_REGISTRY_CONTAINER_NAME,
    KPI_REGISTRY_ITEM_ID,
    KPI_REGISTRY_PARTITION_VALUE,
    require_tool_key,
)
from ada.processes.kpi_materialization.errors import (
    KpiMaterializationAcquisitionError,
    KpiMaterializationRegistryPending,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError


class KpiRegistryReader(Protocol):
    def read(self) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class CosmosKpiRegistryRepository:
    tool_key: str
    client: CosmosClient

    def __post_init__(self) -> None:
        require_tool_key(self.tool_key)

    def read(self) -> Mapping[str, Any]:
        try:
            document = self.client.find_item(
                container_name=KPI_REGISTRY_CONTAINER_NAME,
                item_id=KPI_REGISTRY_ITEM_ID,
                partition_key=KPI_REGISTRY_PARTITION_VALUE,
            )
        except CosmosError as error:
            raise KpiMaterializationAcquisitionError(
                f'Could not read KPI Registry projection for {self.tool_key}'
            ) from error
        if document is None:
            raise KpiMaterializationRegistryPending(
                f'KPI Registry projection is not available yet for {self.tool_key}'
            )
        return document
