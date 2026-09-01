from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from ada.configuration.kpi_definition.errors import KpiDefinitionValidationError
from ada.configuration.kpi_definition.identity import require_kpi_key
from ada.configuration.kpi_definition.models import KpiDefinitionConfiguration


class KpiDefinitionCoverageStatus(StrEnum):
    DEFINED = 'defined'
    MISSING = 'missing'


@dataclass(frozen=True, slots=True)
class KpiDefinitionAuthorityCatalog:
    kpi_configuration_revision: str
    kpi_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = (
            self.kpi_configuration_revision.strip()
            if isinstance(self.kpi_configuration_revision, str)
            else ''
        )
        if not revision:
            raise KpiDefinitionValidationError('KPI configuration revision must not be empty')
        if not isinstance(self.kpi_keys, tuple):
            raise KpiDefinitionValidationError('KPI authority keys must be a tuple')
        keys = tuple(require_kpi_key(key) for key in self.kpi_keys)
        if len(keys) != len(set(keys)):
            raise KpiDefinitionValidationError('KPI authority keys must be unique')
        object.__setattr__(self, 'kpi_configuration_revision', revision)
        object.__setattr__(self, 'kpi_keys', keys)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self.kpi_keys)


@dataclass(frozen=True, slots=True)
class KpiDefinitionCoverageItem:
    kpi_key: str
    status: KpiDefinitionCoverageStatus
    fields: Mapping[str, str | None]

    def __post_init__(self) -> None:
        key = require_kpi_key(self.kpi_key)
        if not isinstance(self.status, KpiDefinitionCoverageStatus):
            raise KpiDefinitionValidationError('KPI definition coverage status is invalid')
        normalized: dict[str, str | None] = {}
        for name, value in self.fields.items():
            if not isinstance(name, str) or not name.strip():
                raise KpiDefinitionValidationError(
                    'KPI definition coverage field name must not be empty'
                )
            if value is not None and not isinstance(value, str):
                raise KpiDefinitionValidationError(
                    'KPI definition coverage field value must be string or null'
                )
            normalized[name.strip()] = value
        if self.status is KpiDefinitionCoverageStatus.MISSING and normalized:
            raise KpiDefinitionValidationError(
                'Missing KPI definition coverage must not contain fields'
            )
        object.__setattr__(self, 'kpi_key', key)
        object.__setattr__(self, 'fields', MappingProxyType(normalized))

    def to_document(self) -> dict[str, object]:
        return {
            'kpi_key': self.kpi_key,
            'status': self.status.value,
            'fields': dict(self.fields),
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> KpiDefinitionCoverageItem:
        try:
            fields = document['fields']
            if not isinstance(fields, Mapping):
                raise TypeError
            return cls(
                kpi_key=document['kpi_key'],
                status=KpiDefinitionCoverageStatus(document['status']),
                fields=fields,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, KpiDefinitionValidationError):
                raise
            raise KpiDefinitionValidationError(
                'KPI definition coverage contract is invalid'
            ) from error


def build_kpi_definition_coverage(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog,
) -> tuple[KpiDefinitionCoverageItem, ...]:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise KpiDefinitionValidationError('KPI definition configuration is invalid')
    if not isinstance(authority, KpiDefinitionAuthorityCatalog):
        raise KpiDefinitionValidationError('KPI definition authority is invalid')
    definitions = {definition.kpi_key: definition for definition in configuration.definitions}
    return tuple(
        KpiDefinitionCoverageItem(
            kpi_key=kpi_key,
            status=(
                KpiDefinitionCoverageStatus.DEFINED
                if kpi_key in definitions
                else KpiDefinitionCoverageStatus.MISSING
            ),
            fields=(definitions[kpi_key].fields if kpi_key in definitions else {}),
        )
        for kpi_key in authority.kpi_keys
    )
