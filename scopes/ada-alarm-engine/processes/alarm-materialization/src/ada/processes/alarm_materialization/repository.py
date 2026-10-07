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

_QUERY = 'SELECT * FROM c WHERE c.id = @item_id'


class AlarmConfigurationReader(Protocol):
    def read_active(self) -> AlarmMaterializationCandidate: ...


@dataclass(frozen=True, slots=True)
class CosmosAlarmConfigurationRepositorySettings:
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
            documents = self.client.query_items(
                container_name=self.settings.container_name,
                query=_QUERY,
                parameters=({'name': '@item_id', 'value': item_id},),
                partition_key=ALARM_CONFIGURATION_SOURCE_KEY,
                max_items=1,
            )
        except CosmosError as error:
            raise AlarmMaterializationAcquisitionError(
                'Could not read Alarm Configuration projection'
            ) from error
        if not documents:
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
        return AlarmMaterializationCandidate.capture(projection)
