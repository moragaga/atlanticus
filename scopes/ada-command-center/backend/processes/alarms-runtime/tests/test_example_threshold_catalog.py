from __future__ import annotations

import io
import tokenize
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ada_command_center.alarms.core import (
    AlarmRouting,
    AlarmStatus,
    EvaluationContext,
    EvaluationErrorOrigin,
    PlannedAlarm,
    execute_evaluator,
)
from ada_command_center.domain.alarms import AlarmIdentity, AlarmKind, Criticality
from ada_command_center.processes.alarms_runtime import (
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)
from ada_command_center.processes.alarms_runtime.catalog import build_alarm_evaluator_registry
from ada_command_center.processes.alarms_runtime.catalog.examples.threshold import (
    build_threshold_contract,
)
from ada_command_center.processes.alarms_runtime.catalog.examples.threshold.requirements import (
    THRESHOLD_REQUIREMENTS,
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
from atlanticus.operational_data.sources import PandasRuntimeFrameContext

_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
_ROOT = Path(__file__).parents[1]


def _planned(key: str, order: int = 1, evaluator_key: str = 'threshold') -> PlannedAlarm:
    return PlannedAlarm(
        identity=AlarmIdentity(family_key='mina', alarm_key=key),
        kind=AlarmKind.RISK,
        criticality=Criticality.C3,
        priority_group='mina',
        priority_order=order,
        evaluator_key=evaluator_key,
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        routing=AlarmRouting(origin_tool_key='mine'),
    )


def _example_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=(build_threshold_contract(),))


def _session(*plans: PlannedAlarm, parameters_by_alarm=None):
    return build_alarm_execution_session(
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        planned_alarms=plans,
        evaluator_registry=_example_registry(),
        parameters_by_alarm=parameters_by_alarm,
    )


def _context(alarm: PlannedAlarm, parameters, values) -> EvaluationContext:
    frames = {
        DataSourceView(DataSource.PI_INTERPOLATED, DataPartition.DAILY): PandasRuntimeFrameContext(
            pd.DataFrame({'temperature': values}),
            ('temperature',),
        )
    }
    return EvaluationContext(
        alarm_identity=alarm.identity,
        now=_AT,
        parameters=parameters,
        data=DataRuntimeContext(frames=frames),
    )


def test_productive_registry_excludes_example() -> None:
    assert build_alarm_evaluator_registry().contracts == ()


def test_example_keeps_developer_requirements_independent_from_web_parameters() -> None:
    first, second = _planned('first', 1), _planned('second', 2)
    session = _session(
        first,
        second,
        parameters_by_alarm={
            first.identity: {},
            second.identity: {'limit': 90.0, 'other_business_input': 'unused'},
        },
    )
    assert len(session.data_plan.views) == 1
    view = session.data_plan.views[0]
    assert view.source is DataSource.PI_INTERPOLATED
    assert view.partition is DataPartition.DAILY
    assert tuple(column.name for column in view.columns) == ('temperature',)
    assert tuple(window.value for window in view.time_windows) == (4,)
    assert session.entry_for(first.identity).requirements == THRESHOLD_REQUIREMENTS
    assert session.entry_for(second.identity).requirements == THRESHOLD_REQUIREMENTS
    assert session.entry_for(first.identity).parameters == {}
    assert session.entry_for(second.identity).parameters['limit'] == 90.0


def test_optional_business_limit_and_effective_evidence() -> None:
    alarm = _planned('first')
    entry = _session(alarm).entry_for(alarm.identity)
    by_default = execute_evaluator(
        alarm,
        _context(alarm, entry.parameters, [70.0, 82.0]),
        entry.evaluator,
    )
    assert by_default.status is AlarmStatus.ACTIVE
    assert by_default.evidence_snapshot.contract_key == 'mina.threshold'
    assert by_default.evidence_snapshot.contract_version == 'v1'
    assert by_default.evidence_snapshot.payload['limit'] == 80.0
    assert by_default.evidence_snapshot.payload['observed_value'] == 82.0

    configured = execute_evaluator(
        alarm,
        _context(alarm, {'limit': 90.0}, [70.0, 82.0]),
        entry.evaluator,
    )
    assert configured.status is AlarmStatus.INACTIVE
    assert configured.evidence_snapshot.payload['limit'] == 90.0
    assert configured.evidence_snapshot.payload['observed_value'] == 82.0


def test_missing_data_is_quality_error_but_invalid_business_parameter_is_evaluator_error() -> None:
    alarm = _planned('first')
    entry = _session(alarm).entry_for(alarm.identity)
    missing = execute_evaluator(
        alarm,
        _context(alarm, {}, []),
        entry.evaluator,
    )
    assert missing.status is AlarmStatus.ERROR
    assert missing.error.origin is EvaluationErrorOrigin.QUALITY
    assert missing.error.error_key == 'insufficient_data'
    assert missing.error.affected_inputs[0].fields == ('temperature',)

    accepted_session = _session(alarm, parameters_by_alarm={alarm.identity: {'limit': 'invalid'}})
    assert accepted_session.entry_for(alarm.identity).requirements == THRESHOLD_REQUIREMENTS
    invalid = execute_evaluator(
        alarm,
        _context(alarm, {'limit': 'invalid'}, [82.0]),
        entry.evaluator,
    )
    assert invalid.status is AlarmStatus.ERROR
    assert invalid.error.origin is EvaluationErrorOrigin.EVALUATOR
    assert invalid.error.error_key == 'evaluator_exception'
    assert invalid.evidence_snapshot is None


def test_one_evaluator_can_declare_multiple_manual_requirements() -> None:
    alarm = _planned('compound', evaluator_key='compound')
    additional = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('temperature', DataColumnType.FLOAT),),
    )
    contract = AlarmEvaluatorContract(
        family_key='mina',
        evaluator_key='compound',
        evaluator=lambda context: None,
        requirements=(*THRESHOLD_REQUIREMENTS, additional),
    )
    session = build_alarm_execution_session(
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        planned_alarms=(alarm,),
        evaluator_registry=AlarmEvaluatorRegistry(contracts=(contract,)),
    )
    assert len(session.entry_for(alarm.identity).requirements) == 2
    assert {view.partition for view in session.data_plan.views} == {
        DataPartition.DAILY,
        DataPartition.LATEST,
    }


def test_new_catalog_mirrors_match_productive_tokens() -> None:
    production = _ROOT / 'src/ada_command_center/processes/alarms_runtime/catalog'
    commented = _ROOT / 'commented/ada_command_center/processes/alarms_runtime/catalog'
    names = tuple(sorted(p.relative_to(production) for p in production.rglob('*.py')))
    assert names == tuple(sorted(p.relative_to(commented) for p in commented.rglob('*.py')))
    ignored = {
        tokenize.COMMENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }

    def tokens(path):
        return [
            (token.type, token.string)
            for token in tokenize.tokenize(io.BytesIO(path.read_bytes()).readline)
            if token.type not in ignored
        ]

    assert all(tokens(production / name) == tokens(commented / name) for name in names)
