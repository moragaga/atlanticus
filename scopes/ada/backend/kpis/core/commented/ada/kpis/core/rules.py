# Contratos de definición KPI; recupera modos explícitos y fija precisión, tipo y dependencias antes de evaluar.
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from numbers import Real
from typing import TypeAlias

from ada.kpis.core.enums import KpiArea, KpiMode, KpiValueKind, KpiValueType
from ada.kpis.core.values import KpiNativeValue
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataRuntimeContext,
    DataSource,
    OperationalScope,
    ShiftSelection,
    TimeWindow,
)

KpiResolver: TypeAlias = Callable[[DataRuntimeContext], object]
OverKpiResolver: TypeAlias = Callable[[Mapping[str, KpiNativeValue]], object]
_KEY_PATTERN = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,119})?')
_NUMERIC_TYPES = frozenset({DataColumnType.INTEGER, DataColumnType.FLOAT})
_SIMPLE_TYPES = frozenset(
    {DataColumnType.TEXT, DataColumnType.INTEGER, DataColumnType.FLOAT, DataColumnType.BOOLEAN}
)


@dataclass(frozen=True, slots=True)
class KpiSpec:
    key: str
    area: KpiArea
    mode: KpiMode
    source: DataSource | None = None
    partition: DataPartition | None = None
    columns: tuple[DataColumn, ...] = ()
    source_requirements: tuple[DataRequirement, ...] = ()
    time_window: TimeWindow | None = None
    operational_scope: OperationalScope | None = None
    shift: ShiftSelection | None = None
    custom_resolver: KpiResolver | None = None
    constant_value: object | None = None
    value_kind: KpiValueKind = KpiValueKind.VALUE
    value_type: KpiValueType | None = None
    decimals: int = 0
    is_truncated: bool = True
    persist_history: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _KEY_PATTERN.fullmatch(self.key):
            raise ValueError(
                'KPI key must use 1-120 letters, numbers, dots, underscores or hyphens'
            )
        if not isinstance(self.area, KpiArea):
            raise TypeError('KPI area must be KpiArea')
        if not isinstance(self.mode, KpiMode):
            raise TypeError('KPI mode must be KpiMode')
        if not isinstance(self.value_kind, KpiValueKind):
            raise TypeError('KPI value_kind must be KpiValueKind')
        if self.value_type is not None and not isinstance(self.value_type, KpiValueType):
            raise TypeError('KPI value_type must be KpiValueType or None')
        _validate_precision(self.decimals, self.is_truncated, prefix='KPI')
        if not isinstance(self.persist_history, bool):
            raise TypeError('persist_history must be bool')
        columns = tuple(self.columns)
        requirements = tuple(self.source_requirements)
        if not all(isinstance(column, DataColumn) for column in columns):
            raise TypeError('KPI columns must contain DataColumn values')
        if not all(isinstance(requirement, DataRequirement) for requirement in requirements):
            raise TypeError('KPI source_requirements must contain DataRequirement values')
        object.__setattr__(self, 'columns', columns)
        object.__setattr__(self, 'source_requirements', requirements)
        self._validate_mode_contract()

    @property
    def requirements(self) -> tuple[DataRequirement, ...]:
        if self.mode is KpiMode.CUSTOM:
            return self.source_requirements
        if self.mode is KpiMode.CONSTANT:
            return ()
        if self.source is None or self.partition is None:
            raise RuntimeError('simple KPI source contract is incomplete')
        return (
            DataRequirement(
                source=self.source,
                partition=self.partition,
                columns=self.columns,
                time_window=self.time_window,
                operational_scope=self.operational_scope,
                shift=self.shift,
            ),
        )

    def _validate_mode_contract(self) -> None:
        if self.mode is KpiMode.CUSTOM:
            self._validate_custom()
            return
        if self.mode is KpiMode.CONSTANT:
            self._validate_constant()
            return
        self._validate_simple()

    def _validate_custom(self) -> None:
        if (
            any(
                value is not None
                for value in (
                    self.source,
                    self.partition,
                    self.time_window,
                    self.operational_scope,
                    self.shift,
                )
            )
            or self.columns
        ):
            raise ValueError(
                'custom KPI must declare source_requirements instead of simple source fields'
            )
        if self.constant_value is not None:
            raise ValueError('custom KPI must not declare constant_value')
        if not self.source_requirements:
            raise ValueError('custom KPI requires source_requirements')
        if not callable(self.custom_resolver):
            raise ValueError('custom KPI requires a callable custom_resolver')
        _validate_output_contract(self.value_kind, self.value_type, prefix='custom KPI')

    def _validate_constant(self) -> None:
        if (
            any(
                value is not None
                for value in (
                    self.source,
                    self.partition,
                    self.time_window,
                    self.operational_scope,
                    self.shift,
                    self.custom_resolver,
                )
            )
            or self.columns
            or self.source_requirements
        ):
            raise ValueError('constant KPI must not declare source, requirement or resolver fields')
        if self.constant_value is None:
            _validate_output_contract(self.value_kind, self.value_type, prefix='constant KPI')
            return
        if self.value_kind is KpiValueKind.JSON:
            if self.value_type is not None:
                raise ValueError('JSON constant KPI must not declare value_type')
            if not isinstance(self.constant_value, list | dict):
                raise TypeError('JSON constant KPI requires a list or dict constant_value')
            return
        if isinstance(self.constant_value, list | dict):
            raise TypeError('VALUE constant KPI requires a scalar constant_value')
        inferred = _value_type_from_scalar(self.constant_value)
        if self.value_type is None:
            object.__setattr__(self, 'value_type', inferred)
        elif not _constant_matches_type(self.constant_value, self.value_type):
            raise TypeError('constant_value does not match declared KPI value_type')

    def _validate_simple(self) -> None:
        if self.source_requirements:
            raise ValueError('simple KPI must not declare source_requirements')
        if self.custom_resolver is not None:
            raise ValueError('simple KPI must not declare custom_resolver')
        if self.constant_value is not None:
            raise ValueError('simple KPI must not declare constant_value')
        if self.value_kind is not KpiValueKind.VALUE:
            raise ValueError('simple KPI must use VALUE value_kind')
        if not isinstance(self.source, DataSource):
            raise TypeError('simple KPI source must be DataSource')
        if not isinstance(self.partition, DataPartition):
            raise TypeError('simple KPI partition must be DataPartition')
        if not self.columns:
            raise ValueError('simple KPI requires at least one typed column')
        allowed = _allowed_types(self.mode)
        invalid = tuple(column for column in self.columns if column.data_type not in allowed)
        if invalid:
            raise ValueError(f'{self.mode.value} KPI contains unsupported column types')
        if (
            self.mode in {KpiMode.LATEST, KpiMode.LATEST_NUMBER, KpiMode.STATUS}
            and len(self.columns) != 1
        ):
            raise ValueError(f'{self.mode.value} KPI requires exactly one column')
        inferred = _simple_value_type(self.mode, self.columns)
        if self.value_type is None:
            object.__setattr__(self, 'value_type', inferred)
        elif self.value_type is not inferred:
            raise ValueError(
                f'{self.mode.value} KPI value_type must match its typed column contract'
            )
        _ = self.requirements


@dataclass(frozen=True, slots=True)
class OverKpiSpec:
    key: str
    area: KpiArea
    dependencies: tuple[str, ...]
    resolver: OverKpiResolver
    value_kind: KpiValueKind = KpiValueKind.VALUE
    value_type: KpiValueType | None = None
    decimals: int = 0
    is_truncated: bool = True
    persist_history: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _KEY_PATTERN.fullmatch(self.key):
            raise ValueError(
                'Over KPI key must use 1-120 letters, numbers, dots, underscores or hyphens'
            )
        if not isinstance(self.area, KpiArea):
            raise TypeError('Over KPI area must be KpiArea')
        dependencies = tuple(self.dependencies)
        if not dependencies:
            raise ValueError('Over KPI requires at least one dependency')
        if any(
            not isinstance(dependency, str) or not _KEY_PATTERN.fullmatch(dependency)
            for dependency in dependencies
        ):
            raise ValueError('Over KPI dependencies must use valid KPI identities')
        if len(set(dependencies)) != len(dependencies):
            raise ValueError('Over KPI dependencies must be unique')
        if self.key in dependencies:
            raise ValueError('Over KPI cannot depend on itself')
        if not callable(self.resolver):
            raise TypeError('Over KPI resolver must be callable')
        if not isinstance(self.value_kind, KpiValueKind):
            raise TypeError('Over KPI value_kind must be KpiValueKind')
        if self.value_type is not None and not isinstance(self.value_type, KpiValueType):
            raise TypeError('Over KPI value_type must be KpiValueType or None')
        _validate_output_contract(self.value_kind, self.value_type, prefix='Over KPI')
        _validate_precision(self.decimals, self.is_truncated, prefix='Over KPI')
        if not isinstance(self.persist_history, bool):
            raise TypeError('Over KPI persist_history must be bool')
        object.__setattr__(self, 'dependencies', dependencies)


def _validate_output_contract(
    value_kind: KpiValueKind,
    value_type: KpiValueType | None,
    *,
    prefix: str,
) -> None:
    if value_kind is KpiValueKind.JSON:
        if value_type is not None:
            raise ValueError(f'{prefix} JSON output must not declare value_type')
        return
    if value_type is None:
        raise ValueError(f'{prefix} VALUE output requires value_type')


def _validate_precision(decimals: int, is_truncated: bool, *, prefix: str) -> None:
    if isinstance(decimals, bool) or not isinstance(decimals, int):
        raise TypeError(f'{prefix} decimals must be an int')
    if not 0 <= decimals <= 12:
        raise ValueError(f'{prefix} decimals must be between 0 and 12')
    if not isinstance(is_truncated, bool):
        raise TypeError(f'{prefix} is_truncated must be bool')


def _allowed_types(mode: KpiMode) -> frozenset[DataColumnType]:
    if mode in {
        KpiMode.LATEST_NUMBER,
        KpiMode.SUM,
        KpiMode.MAX,
        KpiMode.SUM_LATESTS_NUMBERS,
        KpiMode.MAX_LATESTS_NUMBERS,
    }:
        return _NUMERIC_TYPES
    if mode in {KpiMode.LATEST, KpiMode.STATUS}:
        return _SIMPLE_TYPES
    raise ValueError(f'unsupported simple KPI mode: {mode.value}')


def _simple_value_type(mode: KpiMode, columns: tuple[DataColumn, ...]) -> KpiValueType:
    if mode in {
        KpiMode.SUM,
        KpiMode.MAX,
        KpiMode.SUM_LATESTS_NUMBERS,
        KpiMode.MAX_LATESTS_NUMBERS,
    }:
        return (
            KpiValueType.FLOAT
            if any(column.data_type is DataColumnType.FLOAT for column in columns)
            else KpiValueType.INTEGER
        )
    return _column_value_type(columns[0].data_type)


def _column_value_type(value: DataColumnType) -> KpiValueType:
    mapping = {
        DataColumnType.TEXT: KpiValueType.TEXT,
        DataColumnType.INTEGER: KpiValueType.INTEGER,
        DataColumnType.FLOAT: KpiValueType.FLOAT,
        DataColumnType.BOOLEAN: KpiValueType.BOOLEAN,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise ValueError(f'unsupported KPI scalar column type: {value.value}') from error


def _value_type_from_scalar(value: object) -> KpiValueType:
    item = getattr(value, 'item', None)
    if callable(item):
        resolved = item()
        if resolved is not value:
            return _value_type_from_scalar(resolved)
    if isinstance(value, bool):
        return KpiValueType.BOOLEAN
    if isinstance(value, int):
        return KpiValueType.INTEGER
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('constant KPI numeric value must be finite')
        return KpiValueType.FLOAT
    if isinstance(value, str):
        return KpiValueType.TEXT
    raise TypeError('VALUE constant KPI requires a text, integer, float or boolean value')


def _constant_matches_type(value: object, value_type: KpiValueType) -> bool:
    item = getattr(value, 'item', None)
    if callable(item):
        resolved = item()
        if resolved is not value:
            return _constant_matches_type(resolved, value_type)
    if value_type is KpiValueType.TEXT:
        return isinstance(value, str)
    if value_type is KpiValueType.BOOLEAN:
        return isinstance(value, bool)
    if value_type is KpiValueType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, Real) and not isinstance(value, bool)
