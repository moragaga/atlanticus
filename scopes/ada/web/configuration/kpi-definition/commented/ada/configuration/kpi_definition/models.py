from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ada.configuration.kpi_definition.errors import KpiDefinitionValidationError
from ada.configuration.kpi_definition.identity import require_field_name, require_kpi_key

# El contenido descriptivo permanece flexible: nombre de campo -> texto o null.
KpiDefinitionFields = Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class KpiDefinition:
    kpi_key: str
    fields: KpiDefinitionFields

    def __post_init__(self) -> None:
        # Normaliza únicamente la identidad y los nombres; el texto se preserva tal como fue publicado.
        key = require_kpi_key(self.kpi_key)
        normalized_fields: dict[str, str | None] = {}
        for raw_name, value in self.fields.items():
            name = require_field_name(raw_name)
            if name in normalized_fields:
                raise KpiDefinitionValidationError('KPI definition field names must be unique')
            if value is not None and not isinstance(value, str):
                raise KpiDefinitionValidationError(
                    'KPI definition field values must be strings or null'
                )
            normalized_fields[name] = value
        object.__setattr__(self, 'kpi_key', key)
        # Congela el mapping para que una configuración publicada no cambie desde afuera.
        object.__setattr__(self, 'fields', MappingProxyType(normalized_fields))

    def to_document(self) -> dict[str, object]:
        return {'kpi_key': self.kpi_key, 'fields': dict(self.fields)}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> KpiDefinition:
        try:
            fields = document['fields']
            if not isinstance(fields, dict):
                raise TypeError
            return cls(kpi_key=document['kpi_key'], fields=fields)
        except (KeyError, TypeError, ValueError) as error:
            raise KpiDefinitionValidationError('KPI definition contract is invalid') from error


@dataclass(frozen=True, slots=True)
class KpiDefinitionConfiguration:
    definitions: tuple[KpiDefinition, ...] = ()

    def __post_init__(self) -> None:
        definitions = tuple(self.definitions)
        if not all(isinstance(definition, KpiDefinition) for definition in definitions):
            raise KpiDefinitionValidationError(
                'KPI definition configuration contains an invalid definition'
            )
        keys = tuple(definition.kpi_key for definition in definitions)
        if len(keys) != len(set(keys)):
            raise KpiDefinitionValidationError('KPI definition keys must be unique')
        object.__setattr__(self, 'definitions', definitions)

    def definition(self, kpi_key: str) -> KpiDefinition | None:
        normalized = require_kpi_key(kpi_key)
        return next(
            (definition for definition in self.definitions if definition.kpi_key == normalized),
            None,
        )

    def to_document(self) -> dict[str, object]:
        return {'definitions': [definition.to_document() for definition in self.definitions]}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> KpiDefinitionConfiguration:
        try:
            definitions = document.get('definitions', [])
            if not isinstance(definitions, list) or not all(
                isinstance(item, dict) for item in definitions
            ):
                raise TypeError
            return cls(definitions=tuple(KpiDefinition.from_document(item) for item in definitions))
        except (TypeError, ValueError) as error:
            raise KpiDefinitionValidationError(
                'KPI definition configuration contract is invalid'
            ) from error
