from __future__ import annotations

# Modela destinos derivados de la proyección de Tool.
from dataclasses import dataclass

from ada.configuration.kpi_configuration.errors import KpiConfigurationValidationError
from ada.configuration.kpi_configuration.identity import require_destination_key


@dataclass(frozen=True, slots=True)
class KpiDestination:
    key: str
    display_name: str

    def __post_init__(self) -> None:
        key = require_destination_key(self.key)
        display_name = self.display_name.strip() if isinstance(self.display_name, str) else ''
        if not display_name:
            raise KpiConfigurationValidationError(
                'KPI destination display name must not be empty'
            )
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'display_name', display_name)


@dataclass(frozen=True, slots=True)
class KpiDestinationCatalog:
    tool_projection_revision: str
    destinations: tuple[KpiDestination, ...]

    def __post_init__(self) -> None:
        revision = (
            self.tool_projection_revision.strip()
            if isinstance(self.tool_projection_revision, str)
            else ''
        )
        if not revision:
            raise KpiConfigurationValidationError(
                'Tool projection revision must not be empty'
            )
        destinations = tuple(self.destinations)
        if not all(isinstance(item, KpiDestination) for item in destinations):
            raise KpiConfigurationValidationError(
                'KPI destination catalog contains an invalid destination'
            )
        keys = tuple(destination.key for destination in destinations)
        if len(keys) != len(set(keys)):
            raise KpiConfigurationValidationError('KPI destination keys must be unique')
        object.__setattr__(self, 'tool_projection_revision', revision)
        object.__setattr__(self, 'destinations', destinations)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(destination.key for destination in self.destinations)

    def destination(self, key: str) -> KpiDestination | None:
        normalized = require_destination_key(key)
        return next(
            (destination for destination in self.destinations if destination.key == normalized),
            None,
        )
