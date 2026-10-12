# Aísla la lectura puntual de Cosmos y normaliza exclusivamente sus fallas operativas.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ada.web.alarms.collector.contracts import LIVE_CONTAINER, required_key
from ada.web.alarms.collector.models import AlarmLiveReadError
from atlanticus.connectivity.cosmos import CosmosError


# Agrupa una responsabilidad operativa y sus invariantes.
class CosmosDocumentReader(Protocol):
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def find_item(
        self, *, container_name: str, item_id: str, partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmLiveReaderSettings:
    container_name: str = LIVE_CONTAINER

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def __post_init__(self) -> None:
        required_key(self.container_name, 'container_name')


@dataclass(slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class CosmosAlarmLiveReader:
    client: CosmosDocumentReader
    settings: AlarmLiveReaderSettings = field(default_factory=AlarmLiveReaderSettings)

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def __post_init__(self) -> None:
        if not callable(getattr(self.client, 'find_item', None)):
            raise TypeError('Cosmos reader must provide find_item')
        if not isinstance(self.settings, AlarmLiveReaderSettings):
            raise TypeError('Alarm Live reader settings are invalid')

    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def read(self, *, tool_key: str) -> dict[str, Any] | None:
        key = required_key(tool_key, 'tool_key')
        try:
            return self.client.find_item(
                container_name=self.settings.container_name,
                item_id=f'alarm-live:{key}',
                partition_key=key,
            )
        except CosmosError as error:
            raise AlarmLiveReadError('Could not read Alarm Live from Cosmos') from error
