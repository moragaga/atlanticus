# Adapter Cosmos propietario de Command Center para la proyección activa de Alarm Configuration.
# El comportamiento es equivalente al archivo productivo; los comentarios explican ownership y límites.
from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.alarms import (
    AlarmConfigurationSnapshot,
    alarm_configuration_projection_item_id,
)
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
    # El nombre físico pertenece a la composición/provisioning de Command Center, no al contrato compartido.
    container_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.container_name, str)
            or not self.container_name.strip()
            or self.container_name != self.container_name.strip()
        ):
            raise ValueError('Cosmos Alarm Configuration projection container name is invalid')


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

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[AlarmConfigurationSnapshot] | None:
        # Command Center conserva lectura y escritura porque es owner de este recurso Cosmos.
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

    def replace_active(
        self,
        projection: ProjectionRecord[AlarmConfigurationSnapshot],
    ) -> ProjectionRecord[AlarmConfigurationSnapshot]:
        # La identidad del item ya es transversal; el upsert continúa siendo responsabilidad del productor.
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


def _item_id(source_key: SourceKey) -> str:
    # El algoritmo no se duplica: productor y consumidores comparten la misma identidad durable.
    return alarm_configuration_projection_item_id(source_key.value)
