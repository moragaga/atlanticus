from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

import pytest
from ada.contracts.alarms import AlarmIdentity

from ada_command_center.processes.alarms_runtime import (
    AlarmDataSourceAdapter,
    AlarmExecutionIterationError,
    AlarmExecutionSession,
    AlarmIterationData,
    AlarmIterationDataError,
    AlarmIterationLoader,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataRuntimeContext,
    DataSource,
    DataSourceView,
)
from atlanticus.operational_data.planner import (
    DataLoadPlan,
    DataPlanKeyError,
    DataRequirementPlanner,
)

_NOW = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
_RISK = AlarmIdentity(family_key='mill', alarm_key='risk')
_OTHER = AlarmIdentity(family_key='mill', alarm_key='other')


def _requirement(source: DataSource) -> DataRequirement:
    return DataRequirement(
        source=source,
        partition=DataPartition.LATEST,
        columns=(DataColumn(name='value', data_type=DataColumnType.FLOAT),),
    )


def _plan(*, other_source: DataSource | None = None) -> DataLoadPlan:
    shared = _requirement(DataSource.PI_INTERPOLATED)
    return DataRequirementPlanner().plan(
        {
            _RISK.canonical_key: (shared,),
            _OTHER.canonical_key: (shared if other_source is None else _requirement(other_source),),
        }
    )


@dataclass(frozen=True, slots=True)
class _Failure:
    message: str


@dataclass(slots=True)
class _BulkLoaded:
    as_of: datetime
    plan: DataLoadPlan
    failures: dict[DataSourceView, _Failure] = field(default_factory=dict)
    contexts: dict[str, DataRuntimeContext] = field(default_factory=dict)
    requested: list[str] = field(default_factory=list)

    def context_for(self, key: str) -> DataRuntimeContext:
        self.requested.append(key)
        return self.contexts[key]


@dataclass(slots=True)
class _BulkLoader:
    loaded: _BulkLoaded
    calls: list[tuple[DataLoadPlan, datetime]] = field(default_factory=list)

    def load(self, *, plan: DataLoadPlan, as_of: datetime) -> _BulkLoaded:
        self.calls.append((plan, as_of))
        return self.loaded


def test_adapter_loads_merged_plan_once_and_projects_each_alarm_separately() -> None:
    plan = _plan()
    risk = DataRuntimeContext(frames={})
    other = DataRuntimeContext(frames={})
    loaded = _BulkLoaded(
        as_of=_NOW,
        plan=plan,
        contexts={_RISK.canonical_key: risk, _OTHER.canonical_key: other},
    )
    backend = _BulkLoader(loaded)
    adapter = AlarmDataSourceAdapter(source_loader=backend)
    iteration = adapter.load(plan=plan, as_of=_NOW)
    assert isinstance(iteration, AlarmIterationData)
    assert iteration.plan is plan
    assert iteration.as_of == _NOW
    assert iteration.data_for(_RISK) is risk
    assert iteration.data_for(_OTHER) is other
    assert backend.calls == [(plan, _NOW)]
    assert loaded.requested == [_RISK.canonical_key, _OTHER.canonical_key]
    assert len(plan.views) == 1


def test_failure_is_attributed_to_affected_alarm_not_siblings() -> None:
    plan = _plan(other_source=DataSource.DISPATCH_STD_SHIFT_STATE)
    other = DataRuntimeContext(frames={})
    loaded = _BulkLoaded(
        as_of=_NOW,
        plan=plan,
        failures={
            DataSourceView(
                source=DataSource.PI_INTERPOLATED, partition=DataPartition.LATEST
            ): _Failure('provider is down'),
        },
        contexts={_OTHER.canonical_key: other},
    )
    iteration = AlarmDataSourceAdapter(_BulkLoader(loaded)).load(plan=plan, as_of=_NOW)
    with pytest.raises(AlarmIterationDataError) as caught:
        iteration.data_for(_RISK)
    assert caught.value.source_key == DataSource.PI_INTERPOLATED.value
    assert caught.value.reason_key == 'source_unavailable'
    assert 'provider is down' not in str(caught.value)
    assert iteration.data_for(_OTHER) is other
    assert loaded.requested == [_OTHER.canonical_key]


def test_unplanned_identity_fails_without_asking_bulk_loader_for_a_context() -> None:
    plan = DataRequirementPlanner().plan(
        {_RISK.canonical_key: (_requirement(DataSource.PI_INTERPOLATED),)}
    )
    loaded = _BulkLoaded(as_of=_NOW, plan=plan)
    iteration = AlarmDataSourceAdapter(_BulkLoader(loaded)).load(plan=plan, as_of=_NOW)
    with pytest.raises(DataPlanKeyError):
        iteration.data_for(_OTHER)
    assert loaded.requested == []
    with pytest.raises(TypeError, match='AlarmIdentity'):
        iteration.data_for('mill/risk')


@pytest.mark.parametrize('wrong', ['plan', 'timestamp', 'fractional'])
def test_backend_cannot_change_requested_plan_or_normalized_time(wrong: str) -> None:
    plan = _plan()
    loaded = _BulkLoaded(as_of=_NOW, plan=plan)
    if wrong == 'plan':
        loaded.plan = DataRequirementPlanner().plan({})
    elif wrong == 'timestamp':
        loaded.as_of = _NOW + timedelta(seconds=1)
    else:
        loaded.as_of = _NOW + timedelta(milliseconds=1)
    with pytest.raises((AlarmExecutionIterationError, ValueError)):
        AlarmDataSourceAdapter(_BulkLoader(loaded)).load(plan=plan, as_of=_NOW)


def test_empty_session_and_timezone_normalization_keep_single_bulk_call() -> None:
    plan = DataRequirementPlanner().plan({})
    loaded = _BulkLoaded(as_of=_NOW, plan=plan)
    backend = _BulkLoader(loaded)
    adapter = AlarmDataSourceAdapter(backend)
    session = AlarmExecutionSession(
        alarm_configuration_revision='alarm-r10',
        tool_registry_revision='tool-r5',
        entries=(),
        data_plan=plan,
    )
    input_time = _NOW.astimezone(timezone(timedelta(hours=-3)))
    iteration = AlarmIterationLoader(session=session, source_loader=adapter).load(as_of=input_time)
    assert iteration.as_of == _NOW
    assert iteration.session is session
    assert backend.calls == [(plan, _NOW)]
    assert loaded.requested == []
