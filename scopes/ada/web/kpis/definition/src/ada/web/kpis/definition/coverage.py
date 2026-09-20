from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.web.kpis.registry.models import KpiRegistry
from ada.web.kpis.definition.errors import KpiDefinitionValidationError
from ada.web.kpis.definition.identity import require_kpi_key
from ada.web.kpis.definition.models import KpiDefinitionConfiguration


class KpiDefinitionCoverageStatus(StrEnum):
    DEFINED = 'defined'
    MISSING = 'missing'


@dataclass(frozen=True, slots=True)
class KpiDefinitionCoverageItem:
    kpi_key: str
    status: KpiDefinitionCoverageStatus
    fields: dict[str, str | None]

    def __post_init__(self) -> None:
        key = require_kpi_key(self.kpi_key)
        if not isinstance(self.status, KpiDefinitionCoverageStatus):
            raise KpiDefinitionValidationError('KPI definition coverage status is invalid')
        if not isinstance(self.fields, dict):
            raise KpiDefinitionValidationError('KPI definition coverage fields must be a dict')
        object.__setattr__(self, 'kpi_key', key)
        object.__setattr__(self, 'fields', dict(self.fields))


@dataclass(frozen=True, slots=True)
class KpiDefinitionCatalog:
    configuration: KpiDefinitionConfiguration
    coverage: tuple[KpiDefinitionCoverageItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, KpiDefinitionConfiguration):
            raise KpiDefinitionValidationError('KPI definition catalog configuration is invalid')
        coverage = tuple(self.coverage)
        if not all(isinstance(item, KpiDefinitionCoverageItem) for item in coverage):
            raise KpiDefinitionValidationError('KPI definition catalog coverage is invalid')
        keys = tuple(item.kpi_key for item in coverage)
        if len(keys) != len(set(keys)):
            raise KpiDefinitionValidationError('KPI definition catalog coverage keys must be unique')
        object.__setattr__(self, 'coverage', coverage)

    def coverage_item(self, kpi_key: str) -> KpiDefinitionCoverageItem | None:
        key = require_kpi_key(kpi_key)
        return next((item for item in self.coverage if item.kpi_key == key), None)

    @property
    def missing_kpi_keys(self) -> frozenset[str]:
        return frozenset(
            item.kpi_key
            for item in self.coverage
            if item.status is KpiDefinitionCoverageStatus.MISSING
        )


def validate_kpi_definition_configuration(
    configuration: KpiDefinitionConfiguration,
    kpi_registry: KpiRegistry,
) -> None:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise KpiDefinitionValidationError('KPI definition configuration is invalid')
    if not isinstance(kpi_registry, KpiRegistry):
        raise KpiDefinitionValidationError('KPI Registry projection is invalid')
    available = kpi_registry.kpi_keys
    for definition in configuration.definitions:
        if definition.kpi_key not in available:
            raise KpiDefinitionValidationError(
                f'KPI definition {definition.kpi_key!r} is not configured'
            )


def build_kpi_definition_coverage(
    configuration: KpiDefinitionConfiguration,
    kpi_registry: KpiRegistry,
) -> tuple[KpiDefinitionCoverageItem, ...]:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise KpiDefinitionValidationError('KPI definition configuration is invalid')
    if not isinstance(kpi_registry, KpiRegistry):
        raise KpiDefinitionValidationError('KPI Registry projection is invalid')
    items = []
    for binding in kpi_registry.bindings:
        definition = configuration.definition(binding.kpi_key)
        items.append(
            KpiDefinitionCoverageItem(
                kpi_key=binding.kpi_key,
                status=(
                    KpiDefinitionCoverageStatus.DEFINED
                    if definition is not None
                    else KpiDefinitionCoverageStatus.MISSING
                ),
                fields=dict(definition.fields) if definition is not None else {},
            )
        )
    return tuple(items)
