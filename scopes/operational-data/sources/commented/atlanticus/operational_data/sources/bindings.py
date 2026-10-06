from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from atlanticus.datasets.core.errors import DatasetTargetError
from atlanticus.datasets.core.models import DatasetDefinition
from atlanticus.operational_data.core import DataSource, DataView
from atlanticus.operational_data.sources.errors import DataSourceBindingError


class TimePartitionGranularity(StrEnum):
    DAY = 'day'
    MONTH = 'month'


# Une una vista lógica estable con su materialización y detalles físicos de lectura.
@dataclass(frozen=True, slots=True)
class DataViewBinding:
    view: DataView
    materialization: str
    time_partition_granularity: TimePartitionGranularity | None = None
    timestamp_column: str | None = None
    shift_column: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.view, DataView):
            raise TypeError('view must be DataView')
        materialization = _required_text(self.materialization, 'materialization')
        timestamp = _optional_text(self.timestamp_column)
        shift_column = _optional_text(self.shift_column)
        if self.time_partition_granularity is not None and not isinstance(
            self.time_partition_granularity, TimePartitionGranularity
        ):
            raise TypeError('time_partition_granularity must be TimePartitionGranularity or None')
        if self.time_partition_granularity is not None and timestamp is None:
            raise DataSourceBindingError(
                f'{self.view.value}: time-partitioned view requires timestamp_column'
            )
        if shift_column is not None and self.time_partition_granularity is not None:
            raise DataSourceBindingError(
                f'{self.view.value}: shift view cannot use time partition granularity'
            )
        object.__setattr__(self, 'materialization', materialization)
        object.__setattr__(self, 'timestamp_column', timestamp)
        object.__setattr__(self, 'shift_column', shift_column)


# Agrupa todas las vistas soportadas por una fuente operacional.
@dataclass(frozen=True, slots=True)
class DataSourceBinding:
    source: DataSource
    definition: DatasetDefinition
    views: Mapping[DataView, DataViewBinding]

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(self.definition, DatasetDefinition):
            raise TypeError(f'{self.source.value}: definition must be DatasetDefinition')
        if not isinstance(self.views, Mapping) or not self.views:
            raise DataSourceBindingError(f'{self.source.value}: binding requires views')
        normalized: dict[DataView, DataViewBinding] = {}
        for key, view in self.views.items():
            if not isinstance(key, DataView):
                raise TypeError(f'{self.source.value}: view keys must be DataView values')
            if not isinstance(view, DataViewBinding):
                raise TypeError(f'{self.source.value}/{key.value}: invalid view binding')
            if view.view is not key:
                raise DataSourceBindingError(
                    f'{self.source.value}/{key.value}: view key and binding must match'
                )
            try:
                self.definition.get_materialization(view.materialization)
            except DatasetTargetError as error:
                raise DataSourceBindingError(
                    f'{self.source.value}/{key.value}: unknown materialization: '
                    f'{view.materialization}'
                ) from error
            normalized[key] = view
        object.__setattr__(self, 'views', MappingProxyType(normalized))

    def get_view(self, view: DataView) -> DataViewBinding:
        if not isinstance(view, DataView):
            raise TypeError('view must be DataView')
        try:
            return self.views[view]
        except KeyError as error:
            raise DataSourceBindingError(
                f'{self.source.value}: source does not support view: {view.value}'
            ) from error


# Autoridad de bindings disponibles para el loader.
@dataclass(frozen=True, slots=True)
class DataSourceRegistry:
    bindings: Mapping[DataSource, DataSourceBinding]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, Mapping):
            raise TypeError('bindings must be a mapping')
        normalized: dict[DataSource, DataSourceBinding] = {}
        for source, binding in self.bindings.items():
            if not isinstance(source, DataSource):
                raise TypeError('registry keys must be DataSource values')
            if not isinstance(binding, DataSourceBinding):
                raise TypeError(f'{source.value}: binding must be DataSourceBinding')
            if binding.source is not source:
                raise DataSourceBindingError(
                    f'{source.value}: registry key and binding source must match'
                )
            normalized[source] = binding
        object.__setattr__(self, 'bindings', MappingProxyType(normalized))

    @property
    def sources(self) -> tuple[DataSource, ...]:
        return tuple(self.bindings)

    def get(self, source: DataSource) -> DataSourceBinding:
        if not isinstance(source, DataSource):
            raise TypeError('source must be DataSource')
        try:
            return self.bindings[source]
        except KeyError as error:
            raise DataSourceBindingError(
                f'{source.value}: source has no registered binding'
            ) from error

    def get_view(
        self,
        source: DataSource,
        view: DataView,
    ) -> tuple[DataSourceBinding, DataViewBinding]:
        if not isinstance(source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(view, DataView):
            raise TypeError('view must be DataView')
        binding = self.get(source)
        return binding, binding.get_view(view)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _required_text(value, 'optional text')


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field_name} must be a non-empty string')
    return value.strip()
