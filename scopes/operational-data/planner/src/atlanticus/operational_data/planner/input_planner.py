from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from atlanticus.operational_data.core import (
    DataColumn,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScope,
    OperationalScopeSelection,
    ShiftSelection,
    TimeWindow,
    TimeWindowSelection,
    validate_data_inputs,
)
from atlanticus.operational_data.planner.errors import DataPlanKeyError, DataPlanSchemaError


@dataclass(frozen=True, slots=True)
class DataInputViewLoadPlan:
    source: DataSource
    view: DataView
    columns: tuple[DataColumn, ...]
    time_windows: tuple[TimeWindow, ...] = ()
    operational_scopes: tuple[OperationalScope, ...] = ()
    shifts: tuple[ShiftSelection, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(self.view, DataView):
            raise TypeError('view must be DataView')
        columns = _normalize_columns(self.columns)
        if not columns:
            raise ValueError('input view load plan requires columns')
        time_windows = tuple(self.time_windows)
        operational_scopes = tuple(self.operational_scopes)
        shifts = tuple(self.shifts)
        if not all(isinstance(item, TimeWindow) for item in time_windows):
            raise TypeError('time_windows must contain TimeWindow values')
        if not all(isinstance(item, OperationalScope) for item in operational_scopes):
            raise TypeError('operational_scopes must contain OperationalScope values')
        if not all(isinstance(item, ShiftSelection) for item in shifts):
            raise TypeError('shifts must contain ShiftSelection values')
        for name, values in (
            ('time_windows', time_windows),
            ('operational_scopes', operational_scopes),
            ('shifts', shifts),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f'{name} must not contain duplicates')
        object.__setattr__(self, 'columns', columns)
        object.__setattr__(self, 'time_windows', time_windows)
        object.__setattr__(self, 'operational_scopes', operational_scopes)
        object.__setattr__(self, 'shifts', shifts)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def key(self) -> tuple[DataSource, DataView]:
        return self.source, self.view


@dataclass(frozen=True, slots=True)
class DataInputLoadPlan:
    views: tuple[DataInputViewLoadPlan, ...]
    inputs_by_key: Mapping[str, tuple[DataInputSpec, ...]]

    def __post_init__(self) -> None:
        views = tuple(self.views)
        if not all(isinstance(item, DataInputViewLoadPlan) for item in views):
            raise TypeError('views must contain DataInputViewLoadPlan values')
        view_keys = tuple(item.key for item in views)
        if len(view_keys) != len(set(view_keys)):
            raise ValueError('input view load plans must be unique by source and view')
        normalized: dict[str, tuple[DataInputSpec, ...]] = {}
        for key, inputs in self.inputs_by_key.items():
            normalized_key = _required_text(key, 'consumer key')
            normalized[normalized_key] = validate_data_inputs(tuple(inputs))
        object.__setattr__(self, 'views', views)
        object.__setattr__(self, 'inputs_by_key', MappingProxyType(normalized))

    @property
    def sources(self) -> tuple[DataSource, ...]:
        return tuple(dict.fromkeys(plan.source for plan in self.views))

    def view_plan(self, source: DataSource, view: DataView) -> DataInputViewLoadPlan:
        if not isinstance(source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(view, DataView):
            raise TypeError('view must be DataView')
        for plan in self.views:
            if plan.source is source and plan.view is view:
                return plan
        raise DataPlanKeyError(f'{source.value}/{view.value}: view is not part of this load plan')

    def inputs_for(self, key: str) -> tuple[DataInputSpec, ...]:
        normalized = _required_text(key, 'consumer key')
        try:
            return self.inputs_by_key[normalized]
        except KeyError as error:
            raise DataPlanKeyError(
                f'{normalized}: consumer is not part of this load plan'
            ) from error


class DataInputPlanner:
    def plan(
        self,
        inputs_by_key: Mapping[str, tuple[DataInputSpec, ...]],
    ) -> DataInputLoadPlan:
        if not isinstance(inputs_by_key, Mapping):
            raise TypeError('inputs_by_key must be a mapping')
        normalized: dict[str, tuple[DataInputSpec, ...]] = {}
        grouped: dict[tuple[DataSource, DataView], list[DataInputSpec]] = {}
        view_order: list[tuple[DataSource, DataView]] = []
        for key, inputs in inputs_by_key.items():
            normalized_key = _required_text(key, 'consumer key')
            copied = validate_data_inputs(tuple(inputs))
            normalized[normalized_key] = copied
            for input_spec in copied:
                view_key = input_spec.source, input_spec.view
                if view_key not in grouped:
                    grouped[view_key] = []
                    view_order.append(view_key)
                grouped[view_key].append(input_spec)
        views = tuple(
            _merge_inputs(source=source, view=view, inputs=grouped[(source, view)])
            for source, view in view_order
        )
        return DataInputLoadPlan(views=views, inputs_by_key=normalized)


def _merge_inputs(
    *,
    source: DataSource,
    view: DataView,
    inputs: list[DataInputSpec],
) -> DataInputViewLoadPlan:
    columns: list[DataColumn] = []
    time_windows: list[TimeWindow] = []
    operational_scopes: list[OperationalScope] = []
    shifts: list[ShiftSelection] = []
    for input_spec in inputs:
        _extend_unique_columns(columns, input_spec.columns, source=source, view=view)
        selection = input_spec.selection
        if isinstance(selection, TimeWindowSelection):
            if selection.window not in time_windows:
                time_windows.append(selection.window)
        elif isinstance(selection, OperationalScopeSelection):
            if selection.scope not in operational_scopes:
                operational_scopes.append(selection.scope)
        elif isinstance(selection, ShiftSelection) and selection not in shifts:
            shifts.append(selection)
    return DataInputViewLoadPlan(
        source=source,
        view=view,
        columns=tuple(columns),
        time_windows=tuple(time_windows),
        operational_scopes=tuple(operational_scopes),
        shifts=tuple(shifts),
    )


def _extend_unique_columns(
    target: list[DataColumn],
    values: tuple[DataColumn, ...],
    *,
    source: DataSource,
    view: DataView,
) -> None:
    by_name = {column.name: column for column in target}
    for column in values:
        existing = by_name.get(column.name)
        if existing is None:
            target.append(column)
            by_name[column.name] = column
            continue
        if existing.data_type is not column.data_type:
            raise DataPlanSchemaError(
                f'{source.value}/{view.value}: conflicting data types for column {column.name}: '
                f'{existing.data_type.value} != {column.data_type.value}'
            )


def _normalize_columns(values: tuple[DataColumn, ...]) -> tuple[DataColumn, ...]:
    columns = tuple(values)
    if not all(isinstance(column, DataColumn) for column in columns):
        raise TypeError('columns must contain DataColumn values')
    names = tuple(column.name for column in columns)
    if len(names) != len(set(names)):
        raise ValueError('column names must not contain duplicates')
    return columns


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field_name} must be a non-empty string')
    return value.strip()
