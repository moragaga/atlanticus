# Materialización pedagógica del contexto lógico por input_key.
# Un frame amplio por source + view se recorta de forma independiente para cada DataInputSpec.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import pandas as pd

from atlanticus.operational_data.core import (
    DataInputContext,
    DataInputSpec,
    DataSource,
    DataView,
    OperationalScopeSelection,
    ShiftSelection,
    TimeWindowSelection,
    normalize_utc_second,
)
from atlanticus.operational_data.planner import DataInputLoadPlan
from atlanticus.operational_data.sources.bindings import DataSourceRegistry
from atlanticus.operational_data.sources.errors import (
    DataSourceSchemaError,
    DataSourceUnavailableError,
)
from atlanticus.operational_data.sources.frame import PandasRuntimeFrameContext
from atlanticus.operational_data.sources.operational import OperationalWindowResolver
from atlanticus.operational_data.sources.shifts import MineShiftResolver

InputViewKey = tuple[DataSource, DataView]


@dataclass(frozen=True, slots=True)
class DataInputLoadFailure:
    source: DataSource
    view: DataView
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(self.view, DataView):
            raise TypeError('view must be DataView')
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError('message must be non-empty text')
        object.__setattr__(self, 'message', self.message.strip())

    @property
    def key(self) -> InputViewKey:
        return self.source, self.view


@dataclass(frozen=True, slots=True)
class LoadedDataInputView:
    source: DataSource
    view: DataView
    frame: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataSource):
            raise TypeError('source must be DataSource')
        if not isinstance(self.view, DataView):
            raise TypeError('view must be DataView')
        if not isinstance(self.frame, pd.DataFrame):
            raise TypeError('frame must be pandas.DataFrame')
        object.__setattr__(self, 'frame', self.frame.copy(deep=False).reset_index(drop=True))

    @property
    def key(self) -> InputViewKey:
        return self.source, self.view


@dataclass(frozen=True, slots=True)
class LoadedDataInputs:
    as_of: datetime
    plan: DataInputLoadPlan
    registry: DataSourceRegistry
    loaded: Mapping[InputViewKey, LoadedDataInputView]
    failures: Mapping[InputViewKey, DataInputLoadFailure]
    shift_resolver: MineShiftResolver = MineShiftResolver()
    operational_resolver: OperationalWindowResolver = OperationalWindowResolver()

    def __post_init__(self) -> None:
        as_of = normalize_utc_second(self.as_of, field_name='as_of')
        if not isinstance(self.plan, DataInputLoadPlan):
            raise TypeError('plan must be DataInputLoadPlan')
        if not isinstance(self.registry, DataSourceRegistry):
            raise TypeError('registry must be DataSourceRegistry')
        loaded = dict(self.loaded)
        failures = dict(self.failures)
        for key, item in loaded.items():
            if not _valid_key(key) or not isinstance(item, LoadedDataInputView):
                raise TypeError('loaded must map input view keys to LoadedDataInputView')
            if item.key != key:
                raise ValueError('loaded view key must match loaded view value')
        for key, failure in failures.items():
            if not _valid_key(key) or not isinstance(failure, DataInputLoadFailure):
                raise TypeError('failures must map input view keys to DataInputLoadFailure')
            if failure.key != key:
                raise ValueError('failure view key must match failure view value')
        if set(loaded).intersection(failures):
            raise ValueError('an input view cannot be loaded and failed at the same time')
        object.__setattr__(self, 'as_of', as_of)
        object.__setattr__(self, 'loaded', MappingProxyType(loaded))
        object.__setattr__(self, 'failures', MappingProxyType(failures))

    def context_for(self, key: str) -> DataInputContext:
        inputs = self.plan.inputs_for(key)
        # Cada nombre local recibe su slice exacto aunque comparta la misma carga física.
        frames = {
            input_spec.input_key: self._frame_for(input_spec=input_spec) for input_spec in inputs
        }
        return DataInputContext(frames=frames)

    def _frame_for(self, *, input_spec: DataInputSpec) -> PandasRuntimeFrameContext:
        key = input_spec.source, input_spec.view
        failure = self.failures.get(key)
        if failure is not None:
            raise DataSourceUnavailableError(
                input_spec.source,
                f'{input_spec.view.value}: {failure.message}',
            )
        try:
            loaded = self.loaded[key]
        except KeyError as error:
            raise DataSourceUnavailableError(
                input_spec.source,
                f'{input_spec.view.value}: source view was not loaded',
            ) from error
        _, partition_binding = self.registry.get_input_view(input_spec.source, input_spec.view)
        exact = loaded.frame
        selection = input_spec.selection
        if isinstance(selection, TimeWindowSelection):
            exact = _slice_time(
                frame=exact,
                source=input_spec.source.value,
                timestamp_column=partition_binding.timestamp_column,
                start_utc=selection.window.start_from(self.as_of),
                end_utc=self.as_of,
            )
        elif isinstance(selection, OperationalScopeSelection):
            window = self.operational_resolver.resolve(scope=selection.scope, as_of=self.as_of)
            exact = _slice_time(
                frame=exact,
                source=input_spec.source.value,
                timestamp_column=partition_binding.timestamp_column,
                start_utc=window.start_utc,
                end_utc=window.end_utc,
            )
        elif isinstance(selection, ShiftSelection):
            exact = _slice_shift(
                frame=exact,
                source=input_spec.source.value,
                shift_column=partition_binding.shift_column,
                shift_ids=tuple(
                    item.shift_id
                    for item in self.shift_resolver.resolve(selection=selection, as_of=self.as_of)
                ),
            )
        column_names = input_spec.column_names
        missing = tuple(column for column in column_names if column not in exact.columns)
        if missing:
            raise DataSourceSchemaError(
                f'{input_spec.source.value}/{input_spec.view.value}: requested columns '
                f'are missing: {missing}'
            )
        projected = exact.loc[:, list(column_names)].copy(deep=False).reset_index(drop=True)
        return PandasRuntimeFrameContext(projected, column_names)


def _valid_key(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], DataSource)
        and isinstance(value[1], DataView)
    )


def _slice_time(
    *,
    frame: pd.DataFrame,
    source: str,
    timestamp_column: str | None,
    start_utc: datetime,
    end_utc: datetime,
) -> pd.DataFrame:
    if timestamp_column is None:
        raise DataSourceSchemaError(f'{source}: source view has no timestamp column')
    if timestamp_column not in frame.columns:
        raise DataSourceSchemaError(f'{source}: timestamp column is missing: {timestamp_column}')
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors='coerce')
    if timestamps.isna().any():
        raise DataSourceSchemaError(f'{source}: timestamp column contains invalid values')
    return frame.loc[
        (timestamps >= pd.Timestamp(start_utc)) & (timestamps <= pd.Timestamp(end_utc))
    ].copy(deep=False)


def _slice_shift(
    *,
    frame: pd.DataFrame,
    source: str,
    shift_column: str | None,
    shift_ids: tuple[int, ...],
) -> pd.DataFrame:
    if shift_column is None:
        raise DataSourceSchemaError(f'{source}: source view has no shift column')
    if shift_column not in frame.columns:
        raise DataSourceSchemaError(f'{source}: shift column is missing: {shift_column}')
    values = pd.to_numeric(frame[shift_column], errors='coerce')
    return frame.loc[values.isin(shift_ids)].copy(deep=False)
