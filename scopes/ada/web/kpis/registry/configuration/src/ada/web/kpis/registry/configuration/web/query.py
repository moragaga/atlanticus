from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ada.web.kpis.registry.configuration import KpiRegistry, KpiRegistryBinding
from atlanticus.web.pagination import Page, PageRequest, paginate_items


class SortDirection(StrEnum):
    ASC = 'asc'
    DESC = 'desc'


class KpiRegistryDataMode(StrEnum):
    ALL = 'all'
    LATEST = 'latest'
    TIMESERIES = 'timeseries'
    LATEST_AND_TIMESERIES = 'latest_and_timeseries'


class KpiRegistrySortField(StrEnum):
    KPI_KEY = 'kpi_key'
    LATEST = 'latest'
    TIMESERIES = 'timeseries'
    HOURS = 'hours'


@dataclass(frozen=True, slots=True)
class KpiRegistryQuery:
    search: str = ''
    destination_keys: tuple[str, ...] = ()
    data_mode: KpiRegistryDataMode = KpiRegistryDataMode.ALL
    sort_field: KpiRegistrySortField = KpiRegistrySortField.KPI_KEY
    sort_direction: SortDirection = SortDirection.ASC
    page: PageRequest = field(default_factory=PageRequest)

    def __post_init__(self) -> None:
        if not isinstance(self.search, str):
            raise ValueError('KPI configuration search must be text')
        destinations = tuple(
            value.strip()
            for value in self.destination_keys
            if isinstance(value, str) and value.strip()
        )
        if len(destinations) != len(set(destinations)):
            raise ValueError('KPI configuration destination filters must be unique')
        if not isinstance(self.data_mode, KpiRegistryDataMode):
            raise ValueError('KPI configuration data mode is invalid')
        if not isinstance(self.sort_field, KpiRegistrySortField):
            raise ValueError('KPI configuration sort field is invalid')
        if not isinstance(self.sort_direction, SortDirection):
            raise ValueError('KPI configuration sort direction is invalid')
        if not isinstance(self.page, PageRequest):
            raise ValueError('KPI configuration page request is invalid')
        object.__setattr__(self, 'search', self.search.strip())
        object.__setattr__(self, 'destination_keys', destinations)


def query_kpi_configuration(
    configuration: KpiRegistry,
    query: KpiRegistryQuery,
) -> Page[KpiRegistryBinding]:
    if not isinstance(configuration, KpiRegistry):
        raise TypeError('KPI configuration query requires KpiRegistry')
    if not isinstance(query, KpiRegistryQuery):
        raise TypeError('KPI configuration query requires KpiRegistryQuery')

    items = tuple(
        binding
        for binding in configuration.bindings
        if _matches_search(binding, query.search)
        and _matches_destinations(binding, query.destination_keys)
        and _matches_data_mode(binding, query.data_mode)
    )
    sorted_items = _sort_bindings(
        items,
        field=query.sort_field,
        direction=query.sort_direction,
    )
    return paginate_items(sorted_items, query.page)


def _matches_search(binding: KpiRegistryBinding, search: str) -> bool:
    if not search:
        return True
    return search.casefold() in binding.kpi_key.casefold()


def _matches_destinations(
    binding: KpiRegistryBinding,
    destination_keys: tuple[str, ...],
) -> bool:
    if not destination_keys:
        return True
    return any(key in binding.destination_keys for key in destination_keys)


def _matches_data_mode(
    binding: KpiRegistryBinding,
    mode: KpiRegistryDataMode,
) -> bool:
    if mode is KpiRegistryDataMode.ALL:
        return True
    if mode is KpiRegistryDataMode.LATEST:
        return binding.latest_enabled and not binding.series_enabled
    if mode is KpiRegistryDataMode.TIMESERIES:
        return binding.series_enabled and not binding.latest_enabled
    return binding.latest_enabled and binding.series_enabled


def _sort_bindings(
    bindings: tuple[KpiRegistryBinding, ...],
    *,
    field: KpiRegistrySortField,
    direction: SortDirection,
) -> tuple[KpiRegistryBinding, ...]:
    reverse = direction is SortDirection.DESC
    if field is KpiRegistrySortField.KPI_KEY:
        return tuple(sorted(bindings, key=lambda item: item.kpi_key, reverse=reverse))
    if field is KpiRegistrySortField.LATEST:
        return tuple(
            sorted(
                bindings,
                key=lambda item: (item.latest_enabled, item.kpi_key),
                reverse=reverse,
            )
        )
    if field is KpiRegistrySortField.TIMESERIES:
        return tuple(
            sorted(
                bindings,
                key=lambda item: (item.series_enabled, item.kpi_key),
                reverse=reverse,
            )
        )

    valued = tuple(item for item in bindings if item.series_hours is not None)
    empty = tuple(item for item in bindings if item.series_hours is None)
    ordered = tuple(
        sorted(
            valued,
            key=lambda item: (item.series_hours or 0, item.kpi_key),
            reverse=reverse,
        )
    )
    return (*ordered, *empty)
