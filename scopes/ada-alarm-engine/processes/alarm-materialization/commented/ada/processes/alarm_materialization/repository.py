# Repository read-only de la configuración publicada por Command Center.
# No importa CosmosProvisioner ni expone ninguna operación de creación, reparación o escritura.
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmConfigurationProjection,
    AlarmConfigurationProjectionValidationError,
    alarm_configuration_projection_item_id,
)
from ada.processes.alarm_materialization.candidate import AlarmMaterializationCandidate
from ada.processes.alarm_materialization.errors import (
    AlarmMaterializationAcquisitionError,
    AlarmMaterializationConfigurationPending,
    AlarmMaterializationContractError,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError

# Usamos una consulta particionada por id para que un container ausente llegue como error Cosmos,
# mientras que un container válido sin documento produzca una colección vacía y pueda ser PENDING.
_QUERY = 'SELECT * FROM c WHERE c.id = @item_id'


class AlarmConfigurationReader(Protocol):
    def read_active(self) -> AlarmMaterializationCandidate: ...


@dataclass(frozen=True, slots=True)
class CosmosAlarmConfigurationRepositorySettings:
    # El nombre físico lo entrega la composición del proceso; no pertenece al contrato transversal.
    container_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.container_name, str)
            or not self.container_name.strip()
            or self.container_name != self.container_name.strip()
        ):
            raise ValueError('Alarm Configuration Cosmos container name is invalid')


@dataclass(slots=True)
class CosmosAlarmConfigurationRepository:
    client: CosmosClient
    settings: CosmosAlarmConfigurationRepositorySettings

    def __post_init__(self) -> None:
        if not isinstance(self.settings, CosmosAlarmConfigurationRepositorySettings):
            raise TypeError('settings must be CosmosAlarmConfigurationRepositorySettings')

    def read_active(self) -> AlarmMaterializationCandidate:
        item_id = alarm_configuration_projection_item_id(ALARM_CONFIGURATION_SOURCE_KEY)
        try:
            # Esta llamada sólo lee. El proceso no crea el container si Command Center no lo provisionó.
            documents = self.client.query_items(
                container_name=self.settings.container_name,
                query=_QUERY,
                parameters=({'name': '@item_id', 'value': item_id},),
                partition_key=ALARM_CONFIGURATION_SOURCE_KEY,
                max_items=1,
            )
        except CosmosError as error:
            # Container/base/credenciales inválidos son fallas operacionales, nunca espera silenciosa.
            raise AlarmMaterializationAcquisitionError(
                'Could not read Alarm Configuration projection'
            ) from error
        if not documents:
            # Sólo la ausencia del documento dentro de un recurso legible representa espera normal.
            raise AlarmMaterializationConfigurationPending(
                'Alarm Configuration projection is not available yet'
            )
        document = documents[0]
        if (
            document.get('id') != item_id
            or document.get('partition_key') != ALARM_CONFIGURATION_SOURCE_KEY
        ):
            raise AlarmMaterializationContractError(
                'Alarm Configuration projection storage identity is invalid'
            )
        try:
            projection = AlarmConfigurationProjection.from_document(document)
        except AlarmConfigurationProjectionValidationError as error:
            raise AlarmMaterializationContractError(
                'Alarm Configuration projection contract is invalid'
            ) from error
        if projection.source_key != ALARM_CONFIGURATION_SOURCE_KEY:
            raise AlarmMaterializationContractError(
                'Alarm Configuration projection source key is invalid'
            )
        # El resto del flujo recibe evidencia inmutable y deja de conocer Cosmos.
        return AlarmMaterializationCandidate.capture(projection)
