from dataclasses import dataclass

from .errors import AlarmStatusDefinitionError


# Estado visual mínimo: los significados de "activa" y "gestionada" vienen resueltos desde fuera de la UI.
@dataclass(frozen=True, slots=True)
class AlarmStatusState:
    active_count: int
    managed_count: int

    def __post_init__(self) -> None:
        # La presentación sólo acepta conteos válidos; no deriva ni corrige semántica operacional.
        if self.active_count < 0 or self.managed_count < 0:
            raise AlarmStatusDefinitionError('Alarm status counts cannot be negative')
