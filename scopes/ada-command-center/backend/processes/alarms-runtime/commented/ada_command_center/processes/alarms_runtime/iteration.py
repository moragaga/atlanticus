# Espejo comentado: Puerto que desacopla el ciclo de la carga física de Operational Data.
# Mantiene exactamente los mismos tokens ejecutables que el archivo productivo.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ada_command_center.alarms.core import AlarmIdentity
from ada_command_center.processes.alarms_runtime.session import AlarmExecutionSession
from atlanticus.operational_data.core import DataRuntimeContext, normalize_utc_second
from atlanticus.operational_data.planner import DataLoadPlan


class AlarmExecutionIterationError(ValueError):
    pass


class AlarmIterationDataError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        source_key: str | None = None,
        reason_key: str = 'source_unavailable',
    ) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError('message must be non-empty text')
        if source_key is not None and (not isinstance(source_key, str) or not source_key.strip()):
            raise ValueError('source_key must be non-empty text or None')
        if not isinstance(reason_key, str) or not reason_key.strip():
            raise ValueError('reason_key must be non-empty text')
        super().__init__(message.strip())
        self.source_key = None if source_key is None else source_key.strip()
        self.reason_key = reason_key.strip()


@runtime_checkable
class AlarmIterationData(Protocol):
    @property
    def as_of(self) -> datetime: ...

    @property
    def plan(self) -> DataLoadPlan: ...

    def data_for(self, identity: AlarmIdentity) -> DataRuntimeContext: ...


@runtime_checkable
class AlarmIterationSourceLoader(Protocol):
    def load(self, *, plan: DataLoadPlan, as_of: datetime) -> AlarmIterationData: ...


@dataclass(frozen=True, slots=True)
class AlarmExecutionIteration:
    session: AlarmExecutionSession
    data: AlarmIterationData

    def __post_init__(self) -> None:
        if not isinstance(self.session, AlarmExecutionSession):
            raise TypeError('session must be AlarmExecutionSession')
        if not isinstance(self.data, AlarmIterationData):
            raise TypeError('data must implement AlarmIterationData')
        if not isinstance(self.data.plan, DataLoadPlan):
            raise TypeError('iteration data plan must be a DataLoadPlan')
        if self.data.plan != self.session.data_plan:
            raise AlarmExecutionIterationError(
                'iteration data plan must match the execution session data plan'
            )
        normalized_as_of = normalize_utc_second(self.data.as_of, field_name='as_of')
        if normalized_as_of != self.data.as_of:
            raise AlarmExecutionIterationError('iteration data as_of must be normalized to UTC second')

    @property
    def as_of(self) -> datetime:
        return self.data.as_of

    def data_for(self, identity: AlarmIdentity) -> DataRuntimeContext:
        if not isinstance(identity, AlarmIdentity):
            raise TypeError('identity must be AlarmIdentity')
        context = self.data.data_for(identity)
        if not isinstance(context, DataRuntimeContext):
            raise TypeError('iteration data must return DataRuntimeContext')
        return context


@dataclass(slots=True)
class AlarmIterationLoader:
    session: AlarmExecutionSession
    source_loader: AlarmIterationSourceLoader

    def __post_init__(self) -> None:
        if not isinstance(self.session, AlarmExecutionSession):
            raise TypeError('session must be AlarmExecutionSession')
        if not isinstance(self.source_loader, AlarmIterationSourceLoader):
            raise TypeError('source_loader must implement AlarmIterationSourceLoader')

    def load(self, *, as_of: datetime) -> AlarmExecutionIteration:
        normalized_as_of = normalize_utc_second(as_of, field_name='as_of')
        data = self.source_loader.load(
            plan=self.session.data_plan,
            as_of=normalized_as_of,
        )
        if not isinstance(data, AlarmIterationData):
            raise TypeError('source_loader must return AlarmIterationData')
        if data.as_of != normalized_as_of:
            raise AlarmExecutionIterationError(
                'iteration data as_of must match the requested iteration as_of'
            )
        return AlarmExecutionIteration(session=self.session, data=data)
