from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ada.web.kpis.configuration.errors import KpiConfigurationValidationError
from ada.web.kpis.configuration.identity import require_destination_key
from ada.web.kpis.configuration.models import KpiConfiguration
from atlanticus.web.projection.models import ProjectionTarget


@dataclass(frozen=True, slots=True)
class KpiDestination:
    key: str
    display_name: str

    def __post_init__(self) -> None:
        key = require_destination_key(self.key)
        display_name = self.display_name.strip() if isinstance(self.display_name, str) else ''
        if not display_name:
            raise KpiConfigurationValidationError('KPI destination display name must not be empty')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'display_name', display_name)


@dataclass(frozen=True, slots=True)
class KpiDestinationCatalog:
    destinations: tuple[KpiDestination, ...]

    def __post_init__(self) -> None:
        destinations = tuple(self.destinations)
        if not all(isinstance(item, KpiDestination) for item in destinations):
            raise KpiConfigurationValidationError(
                'KPI destination catalog contains an invalid destination'
            )
        keys = tuple(destination.key for destination in destinations)
        if len(keys) != len(set(keys)):
            raise KpiConfigurationValidationError('KPI destination keys must be unique')
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


@dataclass(frozen=True, slots=True)
class KpiDestinationCatalogSnapshot:
    projection_target: ProjectionTarget
    catalog: KpiDestinationCatalog

    def __post_init__(self) -> None:
        if not isinstance(self.projection_target, ProjectionTarget):
            raise KpiConfigurationValidationError('Tool projection target is invalid')
        if not isinstance(self.catalog, KpiDestinationCatalog):
            raise KpiConfigurationValidationError('KPI destination catalog is invalid')


class KpiDestinationCatalogProvider(Protocol):
    def load(self) -> KpiDestinationCatalogSnapshot | None: ...


def validate_kpi_configuration_destinations(
    configuration: KpiConfiguration,
    catalog: KpiDestinationCatalog,
) -> None:
    if not isinstance(configuration, KpiConfiguration):
        raise KpiConfigurationValidationError('KPI configuration is invalid')
    if not isinstance(catalog, KpiDestinationCatalog):
        raise KpiConfigurationValidationError('KPI destination catalog is invalid')
    available = catalog.keys
    for binding in configuration.bindings:
        for destination_key in binding.destination_keys:
            if destination_key not in available:
                raise KpiConfigurationValidationError(
                    f'KPI destination {destination_key!r} is not available'
                )
