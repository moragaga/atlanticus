# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.projection_record import (
    navigation_projection_from_document,
    navigation_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
# Responsabilidad: CosmosNavigationProjectionStoreSettings encapsula una frontera explícita del contrato vigente.
class CosmosNavigationProjectionStoreSettings:
    container_name: str

    # Operación: __post_init__ mantiene la misma semántica que el código productivo.
    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name or container_name != self.container_name:
            raise ValueError('Cosmos navigation projection container name has an invalid format')


# Responsabilidad: CosmosNavigationProjectionStore encapsula una frontera explícita del contrato vigente.
class CosmosNavigationProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    # Operación: __init__ mantiene la misma semántica que el código productivo.
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosNavigationProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosNavigationProjectionStoreSettings):
            raise TypeError('settings must be CosmosNavigationProjectionStoreSettings')
        self._client = client
        self._settings = settings

    # Operación: get_active mantiene la misma semántica que el código productivo.
    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise NavigationConfigurationProjectionError(
                'Could not read Cosmos navigation projection'
            ) from error
        if document is None:
            return None
        projection = navigation_projection_from_document(document)
        if projection.source_key != source_key:
            raise NavigationConfigurationProjectionError(
                'Cosmos navigation projection source key does not match request'
            )
        return projection

    # Operación: replace_active mantiene la misma semántica que el código productivo.
    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        document = navigation_projection_to_document(
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
            raise NavigationConfigurationProjectionError(
                'Could not write Cosmos navigation projection'
            ) from error
        persisted = navigation_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise NavigationConfigurationProjectionError(
                'Cosmos navigation projection persisted a different source key'
            )
        return persisted


# Operación: _cosmos_item_id mantiene la misma semántica que el código productivo.
def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'navigation-projection-{digest}'
