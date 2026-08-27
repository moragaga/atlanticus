from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

# La definición conserva los nombres reales publicados por configuración sin congelar un schema visual.
KpiDefinitionFields = Mapping[str, str | None]


# Representa la definición descriptiva de un KPI y nunca sus measurements operacionales.
@dataclass(frozen=True, slots=True)
class KpiDefinition:
    kpi_key: str
    fields: KpiDefinitionFields

    def __post_init__(self) -> None:
        # La identidad debe existir, pero no se impone aquí un patrón que pueda contradecir KPI Configuration.
        if not isinstance(self.kpi_key, str) or not self.kpi_key.strip():
            raise ValueError('KPI key must be a non-empty string')

        # Se copia el mapping recibido para que el contrato congelado no pueda cambiar desde fuera.
        normalized_fields: dict[str, str | None] = {}
        for field_name, value in self.fields.items():
            if not isinstance(field_name, str) or not field_name.strip():
                raise ValueError('KPI definition field names must be non-empty strings')
            if value is not None and not isinstance(value, str):
                raise ValueError('KPI definition field values must be strings or null')
            normalized_fields[field_name] = value

        # MappingProxyType mantiene los campos arbitrarios, pero los vuelve de sólo lectura.
        object.__setattr__(self, 'fields', MappingProxyType(normalized_fields))


# Es la unidad completa que warmup/refresh intercambiarán más adelante de forma atómica.
@dataclass(frozen=True, slots=True)
class KpiDefinitionSnapshot:
    definitions: tuple[KpiDefinition, ...]

    def __post_init__(self) -> None:
        # Un snapshot ambiguo con dos definiciones para la misma identidad se rechaza antes de almacenarlo.
        keys = [definition.kpi_key for definition in self.definitions]
        if len(keys) != len(set(keys)):
            raise ValueError('Snapshot contains duplicate KPI keys')


# El core sólo conoce este puerto; Cosmos será una implementación inyectada en otro incremento.
@runtime_checkable
class KpiDefinitionProvider(Protocol):
    def load_snapshot(self) -> KpiDefinitionSnapshot: ...


# Expresa found/unavailable sin convertir una ausencia válida en una orden de refrescar la fuente.
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
        # La disponibilidad se deriva de la definición y evita mantener dos estados contradictorios.
        return self.definition is not None
