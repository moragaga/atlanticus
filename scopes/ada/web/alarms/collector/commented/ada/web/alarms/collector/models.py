# Expone estados de disponibilidad y snapshots inmutables como contrato del collector.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmLiveReadError(RuntimeError):
    pass


# Ausencia comprobada del contenedor, distinta del documento ausente.
class AlarmLiveContainerMissingError(AlarmLiveReadError):
    pass


# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorAvailability(StrEnum):
    WAITING = 'waiting'
    READY = 'ready'
    EMPTY = 'empty'
    CONTAINER_MISSING = 'container_missing'
    RETIRED = 'retired'
    MISSING = 'missing'
    INVALID = 'invalid'
    UNAVAILABLE = 'unavailable'


# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorRefreshStatus(StrEnum):
    UPDATED = 'updated'
    UNCHANGED = 'unchanged'
    MISSING = 'missing'


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorSnapshot:
    tool_key: str
    availability: AlarmCollectorAvailability
    semantic_sha256: str | None
    document: dict | None


@dataclass(frozen=True, slots=True)
# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmCollectorRefreshResult:
    status: AlarmCollectorRefreshStatus
    semantic_sha256: str | None = None


# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmDeliveryReader(Protocol):
    # Ejecuta una operación explícita del componente sin añadir acoplamientos.
    def read(self, *, tool_key: str) -> dict | None: ...
