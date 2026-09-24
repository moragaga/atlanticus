# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.configuration.projection_record import (
    alarm_configuration_projection_from_document,
    alarm_configuration_projection_to_document,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosAlarmConfigurationProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.container_name, str)
            or not self.container_name.strip()
            or self.container_name != self.container_name.strip()
        ):
            raise ValueError('Cosmos Alarm Configuration projection container name is invalid')


# Cosmos implementa el mismo ProjectionStore; no lee ni modifica la autoridad histórica Blob.
class CosmosAlarmConfigurationProjectionStore(ProjectionStore[AlarmConfigurationSnapshot]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosAlarmConfigurationProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosAlarmConfigurationProjectionStoreSettings):
            raise TypeError('settings must be CosmosAlarmConfigurationProjectionStoreSettings')
        self._client = client
        self._settings = settings

    # Ausente devuelve None; errores de lectura o datos corruptos se propagan como errores de proyección.
    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[AlarmConfigurationSnapshot] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_item_id(source_key),
                partition_key=source_key.value,
            )
        except CosmosError as error:
            raise AlarmConfigurationProjectionError(
                'Could not read Cosmos Alarm Configuration projection'
            ) from error
        if document is None:
            return None
        projection = alarm_configuration_projection_from_document(document)
        if projection.source_key != source_key:
            raise AlarmConfigurationProjectionError(
                'Cosmos Alarm Configuration projection source key does not match request'
            )
        return projection

    # Se sustituye el head activo para un SourceKey; la selección de la release pertenece al servicio genérico.
    def replace_active(
        self,
        projection: ProjectionRecord[AlarmConfigurationSnapshot],
    ) -> ProjectionRecord[AlarmConfigurationSnapshot]:
        document = alarm_configuration_projection_to_document(
            projection,
            item_id=_item_id(projection.source_key),
            partition_key=projection.source_key.value,
        )
        try:
            saved = self._client.upsert_item(
                container_name=self._settings.container_name,
                item=document,
            )
        except CosmosError as error:
            raise AlarmConfigurationProjectionError(
                'Could not write Cosmos Alarm Configuration projection'
            ) from error
        persisted = alarm_configuration_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise AlarmConfigurationProjectionError(
                'Cosmos Alarm Configuration projection persisted a different source key'
            )
        return persisted


# La identidad estable permite reemplazar el mismo documento sin convertir Cosmos en un historial de releases.
def _item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'ada-command-center-alarm-configuration-projection-{digest}'
