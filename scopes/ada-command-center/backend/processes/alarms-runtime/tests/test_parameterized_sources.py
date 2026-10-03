from __future__ import annotations

import pytest
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality

from ada_command_center.alarms.core import AlarmRouting, PlannedAlarm
from ada_command_center.processes.alarms_runtime import (
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmExecutionSessionError,
    build_alarm_execution_session,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    TimeWindow,
    TimeWindowUnit,
)


def _alarm(name: str) -> PlannedAlarm:
    return PlannedAlarm(
        identity=AlarmIdentity(family_key='mill', alarm_key=name),
        kind=AlarmKind.RISK,
        criticality=Criticality.C3,
        priority_group='mill',
        priority_order={'a': 1, 'b': 2}[name],
        evaluator_key='threshold',
        alarm_configuration_revision='R10',
        tool_registry_revision='T5',
        routing=AlarmRouting(origin_tool_key='mill'),
    )


def _requests(plan: PlannedAlarm, parameters) -> tuple[DataRequirement, ...]:
    return (
        DataRequirement(
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.DAILY,
            columns=(DataColumn(str(parameters['column']), DataColumnType.FLOAT),),
            time_window=TimeWindow(int(parameters['hours']), TimeWindowUnit.HOURS),
        ),
    )


def _registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=lambda context: None,
                requirements_resolver=_requests,
            ),
        ),
    )


def test_alarm_parameters_create_distinct_requirements_and_one_consolidated_view() -> None:
    session = build_alarm_execution_session(
        alarm_configuration_revision='R10',
        tool_registry_revision='T5',
        planned_alarms=(_alarm('a'), _alarm('b')),
        evaluator_registry=_registry(),
        parameters_by_alarm={
            _alarm('a').identity: {'column': 'temperature', 'hours': 1.0},
            _alarm('b').identity: {'column': 'pressure', 'hours': 4.0},
        },
    )
    assert len(session.data_plan.views) == 1
    assert {c.name for c in session.data_plan.views[0].columns} == {'temperature', 'pressure'}
    assert {w.value for w in session.data_plan.views[0].time_windows} == {1, 4}
    assert session.entry_for(_alarm('a').identity).requirements[0].column_names == ('temperature',)
    assert session.entry_for(_alarm('b').identity).requirements[0].column_names == ('pressure',)
    assert session.data_plan.requirements_for(_alarm('a').identity.canonical_key) != (
        session.data_plan.requirements_for(_alarm('b').identity.canonical_key)
    )


def test_invalid_parameterized_requests_fail_before_adoption() -> None:
    with pytest.raises(AlarmExecutionSessionError, match='invalid evaluator data requirements'):
        build_alarm_execution_session(
            alarm_configuration_revision='R10',
            tool_registry_revision='T5',
            planned_alarms=(_alarm('a'),),
            evaluator_registry=_registry(),
            parameters_by_alarm={_alarm('a').identity: {'column': 'temperature', 'hours': 0.0}},
        )


def test_static_and_dynamic_requirements_cannot_compete() -> None:
    with pytest.raises(ValueError, match='mutually exclusive'):
        AlarmEvaluatorContract(
            family_key='mill',
            evaluator_key='threshold',
            evaluator=lambda context: None,
            requirements=(
                DataRequirement(
                    source=DataSource.PI_INTERPOLATED,
                    partition=DataPartition.LATEST,
                    columns=(DataColumn('temperature', DataColumnType.FLOAT),),
                ),
            ),
            requirements_resolver=_requests,
        )
