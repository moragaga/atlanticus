from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.projection_record import (
    ada_access_projection_from_document,
    ada_access_projection_to_document,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosAdaAccessProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name or container_name != self.container_name:
            raise ValueError('Cosmos ADA access projection container name has an invalid format')


class CosmosAdaAccessProjectionStore(ProjectionStore[AdaAccessConfiguration]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosAdaAccessProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosAdaAccessProjectionStoreSettings):
            raise TypeError('settings must be CosmosAdaAccessProjectionStoreSettings')
        self._client = client
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[AdaAccessConfiguration] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise AdaAccessConfigurationProjectionError(
                'Could not read Cosmos ADA access projection'
            ) from error
        if document is None:
            return None
        projection = ada_access_projection_from_document(document)
        if projection.source_key != source_key:
            raise AdaAccessConfigurationProjectionError(
                'Cosmos ADA access projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[AdaAccessConfiguration],
    ) -> ProjectionRecord[AdaAccessConfiguration]:
        document = ada_access_projection_to_document(
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
            raise AdaAccessConfigurationProjectionError(
                'Could not write Cosmos ADA access projection'
            ) from error
        persisted = ada_access_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise AdaAccessConfigurationProjectionError(
                'Cosmos ADA access projection persisted a different source key'
            )
        return persisted


def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'ada-access-projection-{digest}'
