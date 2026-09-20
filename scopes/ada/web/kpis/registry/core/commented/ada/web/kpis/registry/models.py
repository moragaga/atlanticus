# Define el Registry durable y sus bindings operacionales.
# Este archivo es el espejo pedagógico del código productivo equivalente.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.web.kpis.registry.errors import KpiRegistryValidationError
from ada.web.kpis.registry.identity import require_destination_key, require_kpi_key


@dataclass(frozen=True, slots=True)
class KpiRegistryBinding:
    kpi_key: str
    destination_keys: tuple[str, ...]
    latest_enabled: bool = True
    series_enabled: bool = False
    series_hours: int | None = None

    def __post_init__(self) -> None:
        kpi_key = require_kpi_key(self.kpi_key)
        if not isinstance(self.destination_keys, tuple):
            raise KpiRegistryValidationError('KPI destination keys must be a tuple')
        destinations = tuple(require_destination_key(value) for value in self.destination_keys)
        if not destinations:
            raise KpiRegistryValidationError('KPI binding must define at least one destination')
        if len(destinations) != len(set(destinations)):
            raise KpiRegistryValidationError('KPI destination keys must be unique')
        if not isinstance(self.latest_enabled, bool):
            raise KpiRegistryValidationError('KPI latest enabled flag must be boolean')
        if not isinstance(self.series_enabled, bool):
            raise KpiRegistryValidationError('KPI series enabled flag must be boolean')
        if self.series_enabled:
            if (
                isinstance(self.series_hours, bool)
                or not isinstance(self.series_hours, int)
                or not 1 <= self.series_hours <= 24
            ):
                raise KpiRegistryValidationError(
                    'KPI series hours must be between 1 and 24 when series is enabled'
                )
        elif self.series_hours is not None:
            raise KpiRegistryValidationError(
                'KPI series hours must be empty when series is disabled'
            )
        object.__setattr__(self, 'kpi_key', kpi_key)
        object.__setattr__(self, 'destination_keys', destinations)

    @property
    def delivery_enabled(self) -> bool:
        return self.latest_enabled or self.series_enabled

    def to_document(self) -> dict[str, object]:
        return {
            'kpi_key': self.kpi_key,
            'destination_keys': list(self.destination_keys),
            'latest_enabled': self.latest_enabled,
            'series_enabled': self.series_enabled,
            'series_hours': self.series_hours,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> KpiRegistryBinding:
        try:
            destinations = document['destination_keys']
            latest_enabled = document.get('latest_enabled', True)
            series_enabled = document.get('series_enabled', False)
            series_hours = document.get('series_hours')
            if not isinstance(destinations, list):
                raise TypeError
            if not isinstance(latest_enabled, bool) or not isinstance(series_enabled, bool):
                raise TypeError
            if series_hours is not None and (
                isinstance(series_hours, bool) or not isinstance(series_hours, int)
            ):
                raise TypeError
            return cls(
                kpi_key=document['kpi_key'],
                destination_keys=tuple(destinations),
                latest_enabled=latest_enabled,
                series_enabled=series_enabled,
                series_hours=series_hours,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, KpiRegistryValidationError):
                raise
            raise KpiRegistryValidationError('KPI registry binding contract is invalid') from error


@dataclass(frozen=True, slots=True)
class KpiRegistry:
    bindings: tuple[KpiRegistryBinding, ...] = ()

    def __post_init__(self) -> None:
        bindings = tuple(self.bindings)
        if not all(isinstance(binding, KpiRegistryBinding) for binding in bindings):
            raise KpiRegistryValidationError('KPI registry contains an invalid binding')
        keys = tuple(binding.kpi_key for binding in bindings)
        if len(keys) != len(set(keys)):
            raise KpiRegistryValidationError('KPI keys must be unique')
        object.__setattr__(self, 'bindings', bindings)

    @property
    def kpi_keys(self) -> frozenset[str]:
        return frozenset(binding.kpi_key for binding in self.bindings)

    def binding(self, kpi_key: str) -> KpiRegistryBinding | None:
        normalized = require_kpi_key(kpi_key)
        return next(
            (binding for binding in self.bindings if binding.kpi_key == normalized),
            None,
        )

    def to_document(self) -> dict[str, object]:
        return {'bindings': [binding.to_document() for binding in self.bindings]}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> KpiRegistry:
        try:
            bindings = document.get('bindings', [])
            if not isinstance(bindings, list) or not all(
                isinstance(item, Mapping) for item in bindings
            ):
                raise TypeError
            return cls(bindings=tuple(KpiRegistryBinding.from_document(item) for item in bindings))
        except (TypeError, ValueError) as error:
            if isinstance(error, KpiRegistryValidationError):
                raise
            raise KpiRegistryValidationError('KPI registry contract is invalid') from error
