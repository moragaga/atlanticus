from __future__ import annotations

import hashlib
from dataclasses import dataclass

from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.configuration.projection_record import (
    profiles_projection_from_document,
    profiles_projection_to_document,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosProfilesProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name or container_name != self.container_name:
            raise ValueError('Cosmos profiles projection container name has an invalid format')


class CosmosProfilesProjectionStore(ProjectionStore[ProfileCatalog]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosProfilesProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosProfilesProjectionStoreSettings):
            raise TypeError('settings must be CosmosProfilesProjectionStoreSettings')
        self._client = client
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[ProfileCatalog] | None:
        try:
            # Una SourceKey identifica una única Projection activa dentro del container.
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise ProfilesConfigurationProjectionError(
                'Could not read Cosmos profiles projection'
            ) from error
        if document is None:
            return None
        projection = profiles_projection_from_document(document)
        if projection.source_key != source_key:
            raise ProfilesConfigurationProjectionError(
                'Cosmos profiles projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[ProfileCatalog],
    ) -> ProjectionRecord[ProfileCatalog]:
        # El codec agrega id y partition_key sólo en la frontera Cosmos.
        document = profiles_projection_to_document(
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
            raise ProfilesConfigurationProjectionError(
                'Could not write Cosmos profiles projection'
            ) from error
        # La respuesta del provider se vuelve a decodificar para validar el contrato realmente persistido.
        persisted = profiles_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise ProfilesConfigurationProjectionError(
                'Cosmos profiles projection persisted a different source key'
            )
        return persisted


def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'profiles-projection-{digest}'
