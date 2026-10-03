from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ada.contracts.alarms import AlarmIdentity

from ada_command_center.processes.alarms_runtime.iteration import (
    AlarmExecutionIterationError,
    AlarmIterationDataError,
)
from atlanticus.operational_data.core import (
    DataRuntimeContext,
    DataSourceView,
    normalize_utc_second,
)
from atlanticus.operational_data.planner import DataLoadPlan
from atlanticus.operational_data.sources import (
    DataSourceSchemaError,
    DataSourceUnavailableError,
)


@runtime_checkable
class _BulkLoadedSources(Protocol):
    @property
    def as_of(self) -> datetime: ...

    @property
    def plan(self) -> DataLoadPlan: ...

    @property
    def failures(self) -> Mapping[DataSourceView, object]: ...

    def context_for(self, key: str) -> DataRuntimeContext: ...


@runtime_checkable
class _BulkSourceLoader(Protocol):
    def load(self, *, plan: DataLoadPlan, as_of: datetime) -> _BulkLoadedSources: ...


@dataclass(frozen=True, slots=True)
class _AlarmLoadedIterationData:
    loaded: _BulkLoadedSources

    def __post_init__(self) -> None:
        if not isinstance(self.loaded, _BulkLoadedSources):
            raise TypeError('loaded sources must implement the bulk source contract')
        if not isinstance(self.loaded.plan, DataLoadPlan):
            raise TypeError('loaded sources plan must be DataLoadPlan')
        if not isinstance(self.loaded.failures, Mapping):
            raise TypeError('loaded sources failures must be a mapping')

    @property
    def as_of(self) -> datetime:
        return self.loaded.as_of

    @property
    def plan(self) -> DataLoadPlan:
        return self.loaded.plan

    def data_for(self, identity: AlarmIdentity) -> DataRuntimeContext:
        if not isinstance(identity, AlarmIdentity):
            raise TypeError('identity must be AlarmIdentity')
        key = identity.canonical_key
        requirements = self.plan.requirements_for(key)
        for requirement in requirements:
            if requirement.view in self.loaded.failures:
                raise AlarmIterationDataError(
                    'Alarm input source is unavailable',
                    source_key=requirement.source.value,
                    reason_key='source_unavailable',
                )
        try:
            context = self.loaded.context_for(key)
        except DataSourceUnavailableError as error:
            raise AlarmIterationDataError(
                'Alarm input source is unavailable',
                source_key=error.source.value,
                reason_key='source_unavailable',
            ) from error
        except DataSourceSchemaError as error:
            raise AlarmIterationDataError(
                'Alarm input source has an invalid schema',
                reason_key='source_schema_error',
            ) from error
        if not isinstance(context, DataRuntimeContext):
            raise TypeError('loaded sources must return DataRuntimeContext')
        return context


@dataclass(slots=True)
class AlarmDataSourceAdapter:
    source_loader: _BulkSourceLoader

    def __post_init__(self) -> None:
        if not isinstance(self.source_loader, _BulkSourceLoader):
            raise TypeError('source_loader must implement the bulk source loader contract')

    def load(self, *, plan: DataLoadPlan, as_of: datetime) -> _AlarmLoadedIterationData:
        if not isinstance(plan, DataLoadPlan):
            raise TypeError('plan must be DataLoadPlan')
        normalized_at = normalize_utc_second(as_of, field_name='as_of')
        loaded = self.source_loader.load(plan=plan, as_of=normalized_at)
        if not isinstance(loaded, _BulkLoadedSources):
            raise TypeError('source_loader must return bulk loaded sources')
        if not isinstance(loaded.plan, DataLoadPlan) or loaded.plan != plan:
            raise AlarmExecutionIterationError('bulk loaded sources plan must match requested plan')
        normalized_loaded = normalize_utc_second(loaded.as_of, field_name='loaded as_of')
        if loaded.as_of != normalized_loaded or loaded.as_of != normalized_at:
            raise AlarmExecutionIterationError(
                'bulk loaded sources as_of must match normalized requested as_of'
            )
        return _AlarmLoadedIterationData(loaded)
