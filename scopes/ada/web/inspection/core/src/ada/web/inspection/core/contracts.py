from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

KpiDefinitionFields = Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class KpiDefinition:
    kpi_key: str
    fields: KpiDefinitionFields

    def __post_init__(self) -> None:
        if not isinstance(self.kpi_key, str) or not self.kpi_key.strip():
            raise ValueError('KPI key must be a non-empty string')

        normalized_fields: dict[str, str | None] = {}
        for field_name, value in self.fields.items():
            if not isinstance(field_name, str) or not field_name.strip():
                raise ValueError('KPI definition field names must be non-empty strings')
            if value is not None and not isinstance(value, str):
                raise ValueError('KPI definition field values must be strings or null')
            normalized_fields[field_name] = value

        object.__setattr__(self, 'fields', MappingProxyType(normalized_fields))


@dataclass(frozen=True, slots=True)
class KpiDefinitionSnapshot:
    definitions: tuple[KpiDefinition, ...]

    def __post_init__(self) -> None:
        keys = [definition.kpi_key for definition in self.definitions]
        if len(keys) != len(set(keys)):
            raise ValueError('Snapshot contains duplicate KPI keys')


@runtime_checkable
class KpiDefinitionProvider(Protocol):
    def load_snapshot(self) -> KpiDefinitionSnapshot: ...


@dataclass(frozen=True, slots=True)
class KpiInspectionResult:
    kpi_key: str
    definition: KpiDefinition | None

    def __post_init__(self) -> None:
        if not isinstance(self.kpi_key, str) or not self.kpi_key.strip():
            raise ValueError('KPI key must be a non-empty string')
        if self.definition is not None and self.definition.kpi_key != self.kpi_key:
            raise ValueError('Inspection result KPI key does not match definition KPI key')

    @property
    def available(self) -> bool:
        return self.definition is not None
