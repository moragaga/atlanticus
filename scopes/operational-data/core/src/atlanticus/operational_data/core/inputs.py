from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from atlanticus.operational_data.core.contracts import (
    DataColumn,
    DataSource,
    OperationalScope,
    ShiftSelection,
    TimeWindow,
)


class DataView(StrEnum):
    LATEST = 'latest'
    DAILY = 'daily'
    MONTHLY = 'monthly'
    WEEKLY = 'weekly'
    SHIFT = 'shift'


@dataclass(frozen=True, slots=True)
class TimeWindowSelection:
    window: TimeWindow

    def __post_init__(self) -> None:
        if not isinstance(self.window, TimeWindow):
            raise TypeError('window must be TimeWindow')


@dataclass(frozen=True, slots=True)
class OperationalScopeSelection:
    scope: OperationalScope

    def __post_init__(self) -> None:
        if not isinstance(self.scope, OperationalScope):
            raise TypeError('scope must be OperationalScope')


DataSelection: TypeAlias = TimeWindowSelection | OperationalScopeSelection | ShiftSelection | None


@dataclass(frozen=True, slots=True)
class DataInputSpec:
    input_key: str
    source: DataSource
    view: DataView
    columns: tuple[DataColumn, ...]
    selection: DataSelection = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'input_key', _input_key(self.input_key))
        if not isinstance(self.source, DataSource):
            raise TypeError('data input source must be DataSource')
        if not isinstance(self.view, DataView):
            raise TypeError('data input view must be DataView')
        columns = tuple(self.columns)
        if not columns:
            raise ValueError('data input requires at least one column')
        if not all(isinstance(column, DataColumn) for column in columns):
            raise TypeError('data input columns must contain DataColumn values')
        names = tuple(column.name for column in columns)
        if len(names) != len(set(names)):
            raise ValueError('data input column names must be unique')
        if self.selection is not None and not isinstance(
            self.selection,
            TimeWindowSelection | OperationalScopeSelection | ShiftSelection,
        ):
            raise TypeError('data input selection is not supported')
        object.__setattr__(self, 'columns', columns)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


def validate_data_inputs(inputs: tuple[DataInputSpec, ...]) -> tuple[DataInputSpec, ...]:
    resolved = tuple(inputs)
    if not all(isinstance(item, DataInputSpec) for item in resolved):
        raise TypeError('data inputs must contain DataInputSpec values')
    keys = tuple(item.input_key for item in resolved)
    if len(keys) != len(set(keys)):
        raise ValueError('data input keys must be unique')
    return resolved


def _input_key(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError('input_key must be a non-empty string')
    if value != value.strip():
        raise ValueError('input_key must not contain surrounding whitespace')
    return value
