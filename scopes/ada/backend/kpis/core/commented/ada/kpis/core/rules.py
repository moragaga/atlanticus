# Contratos de definición KPI. OverKpiSpec declara dependencias entre KPI ya calculados y no fuentes operacionales.
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from ada.kpis.core.enums import KpiArea, KpiMode, KpiValueKind
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
_SIMPLE_TYPES = frozenset({DataColumnType.TEXT, DataColumnType.INTEGER, DataColumnType.FLOAT})


@dataclass(frozen=True, slots=True)
class KpiSpec:
    key: str
    area: KpiArea | str
    mode: KpiMode
    source: DataSource | None = None
    partition: DataPartition | None = None
    columns: tuple[DataColumn, ...] = ()
    source_requirements: tuple[DataRequirement, ...] = ()
    time_window: TimeWindow | None = None
    operational_scope: OperationalScope | None = None
    shift: ShiftSelection | None = None
    custom_resolver: KpiResolver | None = None
    decimals: int | None = None
    persist_history: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _KEY_PATTERN.fullmatch(self.key):
            raise ValueError(
                'KPI key must use 1-120 letters, numbers, dots, underscores or hyphens'
            )
        area = self.area.value if isinstance(self.area, KpiArea) else self.area
        if not isinstance(area, str) or not _KEY_PATTERN.fullmatch(area):
            raise ValueError('KPI area must use a valid identity')
        if not isinstance(self.mode, KpiMode):
            raise TypeError('KPI mode must be KpiMode')
        if not isinstance(self.persist_history, bool):
            raise TypeError('persist_history must be bool')
        columns = tuple(self.columns)
        requirements = tuple(self.source_requirements)
        if not all(isinstance(column, DataColumn) for column in columns):
            raise TypeError('KPI columns must contain DataColumn values')
        if not all(isinstance(requirement, DataRequirement) for requirement in requirements):
            raise TypeError('KPI source_requirements must contain DataRequirement values')
        object.__setattr__(self, 'area', area)
        object.__setattr__(self, 'columns', columns)
        object.__setattr__(self, 'source_requirements', requirements)
        self._validate_mode_contract()

    @property
    def requirements(self) -> tuple[DataRequirement, ...]:
        if self.mode is KpiMode.CUSTOM:
            return self.source_requirements
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
        if self.decimals is not None:
            if isinstance(self.decimals, bool) or not isinstance(self.decimals, int):
                raise TypeError('KPI decimals must be an int')
            if not 0 <= self.decimals <= 12:
                raise ValueError('KPI decimals must be between 0 and 12')
        if self.mode is KpiMode.CUSTOM:
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
            if self.decimals is not None:
                raise ValueError('custom KPI must not declare decimals')
            if not self.source_requirements:
                raise ValueError('custom KPI requires source_requirements')
            if not callable(self.custom_resolver):
                raise ValueError('custom KPI requires a callable custom_resolver')
            return
        if self.source_requirements:
            raise ValueError('simple KPI must not declare source_requirements')
        if self.custom_resolver is not None:
            raise ValueError('simple KPI must not declare custom_resolver')
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
        if self.decimals is not None and self.mode not in {
            KpiMode.LATEST_NUMBER,
            KpiMode.SUM,
            KpiMode.MAX,
        }:
            raise ValueError('KPI decimals are only valid for numeric modes')
        _ = self.requirements


@dataclass(frozen=True, slots=True)
class OverKpiSpec:
    key: str
    area: KpiArea | str
    dependencies: tuple[str, ...]
    resolver: OverKpiResolver
    value_kind: KpiValueKind = KpiValueKind.VALUE
    decimals: int | None = None
    persist_history: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _KEY_PATTERN.fullmatch(self.key):
            raise ValueError(
                'Over KPI key must use 1-120 letters, numbers, dots, underscores or hyphens'
            )
        area = self.area.value if isinstance(self.area, KpiArea) else self.area
        if not isinstance(area, str) or not _KEY_PATTERN.fullmatch(area):
            raise ValueError('Over KPI area must use a valid identity')
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
        if self.decimals is not None:
            if isinstance(self.decimals, bool) or not isinstance(self.decimals, int):
                raise TypeError('Over KPI decimals must be an int or None')
            if not 0 <= self.decimals <= 12:
                raise ValueError('Over KPI decimals must be between 0 and 12')
            if self.value_kind is KpiValueKind.JSON:
                raise ValueError('JSON Over KPI must not declare decimals')
        if not isinstance(self.persist_history, bool):
            raise TypeError('Over KPI persist_history must be bool')
        object.__setattr__(self, 'area', area)
        object.__setattr__(self, 'dependencies', dependencies)


def _allowed_types(mode: KpiMode) -> frozenset[DataColumnType]:
    if mode in {KpiMode.LATEST_NUMBER, KpiMode.SUM, KpiMode.MAX}:
        return _NUMERIC_TYPES
    if mode in {KpiMode.LATEST, KpiMode.STATUS}:
        return _SIMPLE_TYPES
    raise ValueError(f'unsupported simple KPI mode: {mode.value}')
