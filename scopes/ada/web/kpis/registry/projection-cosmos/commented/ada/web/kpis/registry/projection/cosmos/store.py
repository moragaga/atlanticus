# Lee y reemplaza la proyección Registry usando source_key como partición.
# Este archivo es el espejo pedagógico del código productivo equivalente.

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.registry.configuration.errors import KpiRegistryProjectionError
from ada.web.kpis.registry.configuration.projection_record import (
    kpi_registry_projection_from_document,
    kpi_registry_projection_to_document,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosKpiRegistryProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name or container_name != self.container_name:
            raise ValueError('Cosmos KPI Registry projection container name has an invalid format')


class CosmosKpiRegistryProjectionStore(ProjectionStore[KpiRegistry]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosKpiRegistryProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosKpiRegistryProjectionStoreSettings):
            raise TypeError('settings must be CosmosKpiRegistryProjectionStoreSettings')
        self._client = client
        self._settings = settings

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[KpiRegistry] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise KpiRegistryProjectionError('Could not read Cosmos KPI Registry projection') from error
        if document is None:
            return None
        projection = kpi_registry_projection_from_document(document)
        if projection.source_key != source_key:
            raise KpiRegistryProjectionError(
                'Cosmos KPI Registry projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiRegistry],
    ) -> ProjectionRecord[KpiRegistry]:
        document = kpi_registry_projection_to_document(
            projection,
            item_id=_cosmos_item_id(projection.source_key),
            partition_key=projection.source_key.value,
        )
        try:
            saved = self._client.upsert_item(
                container_name=self._settings.container_name,
                item=document,
            )
        except CosmosError as error:
            raise KpiRegistryProjectionError('Could not write Cosmos KPI Registry projection') from error
        persisted = kpi_registry_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise KpiRegistryProjectionError(
                'Cosmos KPI Registry projection persisted a different source key'
            )
        return persisted


def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'ada-kpi-registry-projection-{digest}'
