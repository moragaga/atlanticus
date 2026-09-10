# Espejo comentado de la superficie Web de KPI Definition.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ada.web.configuration import (
    ConfigurationPage,
    ConfigurationPageRequest,
    paginate_items,
)
from ada.web.kpis.definition import (
    KpiDefinitionAuthorityCatalog,
    KpiDefinitionConfiguration,
    KpiDefinitionCoverageStatus,
    build_kpi_definition_coverage,
)


class KpiDefinitionEditorStatus(StrEnum):
    PENDING = 'pending'
    DEFINED = 'defined'
    ORPHAN = 'orphan'


class KpiDefinitionStatusFilter(StrEnum):
    ALL = 'all'
    PENDING = 'pending'
    DEFINED = 'defined'
    ORPHAN = 'orphan'


@dataclass(frozen=True, slots=True)
class KpiDefinitionEditorItem:
    kpi_key: str
    status: KpiDefinitionEditorStatus
    fields: Mapping[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = self.kpi_key.strip() if isinstance(self.kpi_key, str) else ''
        if not key:
            raise ValueError('KPI definition editor key must not be empty')
        if not isinstance(self.status, KpiDefinitionEditorStatus):
            raise ValueError('KPI definition editor status is invalid')
        normalized = {
            str(name).strip(): value
            for name, value in self.fields.items()
            if str(name).strip()
        }
        if any(value is not None and not isinstance(value, str) for value in normalized.values()):
            raise ValueError('KPI definition editor fields must contain text or null')
        if self.status is KpiDefinitionEditorStatus.PENDING and normalized:
            raise ValueError('Pending KPI definition editor item must not contain fields')
        object.__setattr__(self, 'kpi_key', key)
        object.__setattr__(self, 'fields', MappingProxyType(normalized))

    @property
    def detail(self) -> str | None:
        value = self.fields.get('detail')
        return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class KpiDefinitionQuery:
    search: str = ''
    status: KpiDefinitionStatusFilter = KpiDefinitionStatusFilter.ALL
    page: ConfigurationPageRequest = field(default_factory=ConfigurationPageRequest)

    def __post_init__(self) -> None:
        if not isinstance(self.search, str):
            raise ValueError('KPI definition search must be text')
        if not isinstance(self.status, KpiDefinitionStatusFilter):
            raise ValueError('KPI definition status filter is invalid')
        if not isinstance(self.page, ConfigurationPageRequest):
            raise ValueError('KPI definition page request is invalid')
        object.__setattr__(self, 'search', self.search.strip())


def build_kpi_definition_editor_items(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog | None,
) -> tuple[KpiDefinitionEditorItem, ...]:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise TypeError('KPI definition editor requires KpiDefinitionConfiguration')
    if authority is None:
        return ()
    if not isinstance(authority, KpiDefinitionAuthorityCatalog):
        raise TypeError('KPI definition editor authority is invalid')

    coverage = build_kpi_definition_coverage(configuration, authority)
    items = [
        KpiDefinitionEditorItem(
            kpi_key=item.kpi_key,
            status=(
                KpiDefinitionEditorStatus.DEFINED
                if item.status is KpiDefinitionCoverageStatus.DEFINED
                else KpiDefinitionEditorStatus.PENDING
            ),
            fields=item.fields,
        )
        for item in coverage
    ]

    authority_keys = authority.keys
    items.extend(
        KpiDefinitionEditorItem(
            kpi_key=definition.kpi_key,
            status=KpiDefinitionEditorStatus.ORPHAN,
            fields=definition.fields,
        )
        for definition in configuration.definitions
        if definition.kpi_key not in authority_keys
    )
    return tuple(items)


def query_kpi_definitions(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog | None,
    query: KpiDefinitionQuery,
) -> ConfigurationPage[KpiDefinitionEditorItem]:
    if not isinstance(query, KpiDefinitionQuery):
        raise TypeError('KPI definition query requires KpiDefinitionQuery')

    items = tuple(
        item
        for item in build_kpi_definition_editor_items(configuration, authority)
        if _matches_search(item, query.search) and _matches_status(item, query.status)
    )
    ordered = tuple(sorted(items, key=lambda item: item.kpi_key.casefold()))
    return paginate_items(ordered, query.page)


def _matches_search(item: KpiDefinitionEditorItem, search: str) -> bool:
    return not search or search.casefold() in item.kpi_key.casefold()


def _matches_status(
    item: KpiDefinitionEditorItem,
    status: KpiDefinitionStatusFilter,
) -> bool:
    if status is KpiDefinitionStatusFilter.ALL:
        return True
    return item.status.value == status.value
