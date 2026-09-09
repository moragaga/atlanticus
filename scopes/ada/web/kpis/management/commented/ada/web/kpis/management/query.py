from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ada.web.configuration import (
    ConfigurationPage,
    ConfigurationPageRequest,
    SortDirection,
    paginate_items,
)
from ada.web.kpis.configuration import KpiConfiguration, KpiConfigurationBinding


class KpiConfigurationDataMode(StrEnum):
    ALL = 'all'
    LATEST = 'latest'
    TIMESERIES = 'timeseries'
    LATEST_AND_TIMESERIES = 'latest_and_timeseries'


class KpiConfigurationSortField(StrEnum):
    KPI_KEY = 'kpi_key'
    LATEST = 'latest'
    TIMESERIES = 'timeseries'
    HOURS = 'hours'


@dataclass(frozen=True, slots=True)
class KpiConfigurationQuery:
    search: str = ''
    destination_keys: tuple[str, ...] = ()
    data_mode: KpiConfigurationDataMode = KpiConfigurationDataMode.ALL
    sort_field: KpiConfigurationSortField = KpiConfigurationSortField.KPI_KEY
    sort_direction: SortDirection = SortDirection.ASC
    page: ConfigurationPageRequest = field(default_factory=ConfigurationPageRequest)

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
        if not isinstance(self.data_mode, KpiConfigurationDataMode):
            raise ValueError('KPI configuration data mode is invalid')
        if not isinstance(self.sort_field, KpiConfigurationSortField):
            raise ValueError('KPI configuration sort field is invalid')
        if not isinstance(self.sort_direction, SortDirection):
            raise ValueError('KPI configuration sort direction is invalid')
        if not isinstance(self.page, ConfigurationPageRequest):
            raise ValueError('KPI configuration page request is invalid')
        object.__setattr__(self, 'search', self.search.strip())
        object.__setattr__(self, 'destination_keys', destinations)


def query_kpi_configuration(
    configuration: KpiConfiguration,
    query: KpiConfigurationQuery,
) -> ConfigurationPage[KpiConfigurationBinding]:
    if not isinstance(configuration, KpiConfiguration):
        raise TypeError('KPI management query requires KpiConfiguration')
    if not isinstance(query, KpiConfigurationQuery):
        raise TypeError('KPI management query requires KpiConfigurationQuery')

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


def _matches_search(binding: KpiConfigurationBinding, search: str) -> bool:
    if not search:
        return True
    return search.casefold() in binding.kpi_key.casefold()


def _matches_destinations(
    binding: KpiConfigurationBinding,
    destination_keys: tuple[str, ...],
) -> bool:
    if not destination_keys:
        return True
    return any(key in binding.destination_keys for key in destination_keys)


def _matches_data_mode(
    binding: KpiConfigurationBinding,
    mode: KpiConfigurationDataMode,
) -> bool:
    if mode is KpiConfigurationDataMode.ALL:
        return True
    if mode is KpiConfigurationDataMode.LATEST:
        return binding.latest_enabled and not binding.series_enabled
    if mode is KpiConfigurationDataMode.TIMESERIES:
        return binding.series_enabled and not binding.latest_enabled
    return binding.latest_enabled and binding.series_enabled


def _sort_bindings(
    bindings: tuple[KpiConfigurationBinding, ...],
    *,
    field: KpiConfigurationSortField,
    direction: SortDirection,
) -> tuple[KpiConfigurationBinding, ...]:
    reverse = direction is SortDirection.DESC
    if field is KpiConfigurationSortField.KPI_KEY:
        return tuple(sorted(bindings, key=lambda item: item.kpi_key, reverse=reverse))
    if field is KpiConfigurationSortField.LATEST:
        return tuple(
            sorted(
                bindings,
                key=lambda item: (item.latest_enabled, item.kpi_key),
                reverse=reverse,
            )
        )
    if field is KpiConfigurationSortField.TIMESERIES:
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
