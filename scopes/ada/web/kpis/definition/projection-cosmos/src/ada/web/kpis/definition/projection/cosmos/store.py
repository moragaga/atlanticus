from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.configuration.errors import KpiDefinitionProjectionError
from ada.web.kpis.definition.configuration.projection_record import (
    kpi_definition_projection_from_document,
    kpi_definition_projection_to_document,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosKpiDefinitionProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name or container_name != self.container_name:
            raise ValueError('Cosmos KPI Definition projection container name has an invalid format')


class CosmosKpiDefinitionProjectionStore(ProjectionStore[KpiDefinitionCatalog]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosKpiDefinitionProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosKpiDefinitionProjectionStoreSettings):
            raise TypeError('settings must be CosmosKpiDefinitionProjectionStoreSettings')
        self._client = client
        self._settings = settings

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[KpiDefinitionCatalog] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise KpiDefinitionProjectionError(
                'Could not read Cosmos KPI Definition projection'
            ) from error
        if document is None:
            return None
        projection = kpi_definition_projection_from_document(document)
        if projection.source_key != source_key:
            raise KpiDefinitionProjectionError(
                'Cosmos KPI Definition projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiDefinitionCatalog],
    ) -> ProjectionRecord[KpiDefinitionCatalog]:
        document = kpi_definition_projection_to_document(
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
            raise KpiDefinitionProjectionError(
                'Could not write Cosmos KPI Definition projection'
            ) from error
        persisted = kpi_definition_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise KpiDefinitionProjectionError(
                'Cosmos KPI Definition projection persisted a different source key'
            )
        return persisted


def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'ada-kpi-definition-projection-{digest}'
