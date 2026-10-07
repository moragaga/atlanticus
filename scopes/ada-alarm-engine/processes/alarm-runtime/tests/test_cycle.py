from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmResolutionKey,
    AlarmRouting,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
    EvidenceSnapshot,
    PlannedAlarm,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality
from ada.processes.alarm_runtime import (
    AlarmEvaluationCycle,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)
from atlanticus.operational_data.core import DataColumn, DataColumnType
from atlanticus.operational_data.planner import DataInputLoadPlan
from atlanticus.operational_data.sources import (
    DataInputLoader,
    DataSourceReadError,
    PiInterpolated,
    PiSourceProvider,
    build_current_source_registry,
)

CYCLE_AT = datetime(2026, 10, 7, 20, 15, tzinfo=UTC)


class Reader:
    def __init__(self, frame: pd.DataFrame | None = None, *, fail: bool = False) -> None:
        self.frame = frame
        self.fail = fail
        self.calls = 0

    def read_frame(self, **_kwargs):
        self.calls += 1
        if self.fail:
            raise DataSourceReadError('source failed')
        return self.frame


def _plan(identity: AlarmIdentity, *, evaluator_key: str, priority: int) -> PlannedAlarm:
    return PlannedAlarm(
        identity=identity,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        is_special_condition=False,
        priority_group='group',
        priority_order=priority,
        evaluator_key=evaluator_key,
        alarm_configuration_revision='ALARMS-10',
        tool_registry_revision='TOOLS-4',
        routing=AlarmRouting(origin_tool_key='tool_a'),
    )


def _configuration(*plans: PlannedAlarm) -> EngineAlarmConfiguration:
    identities = tuple(plan.identity for plan in plans)
    return EngineAlarmConfiguration(
        resolution_key=AlarmResolutionKey('ALARMS-10', 'TOOLS-4'),
        defined_alarm_identities=identities,
        planned_alarms=plans,
        parameters_by_alarm={},
    )


def _loader(reader: Reader) -> DataInputLoader:
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    return DataInputLoader(reader=reader, registry=registry)


def test_cycle_freezes_one_time_and_passes_loaded_context_to_evaluator() -> None:
    identity = AlarmIdentity('mill', 'risk')
    observed = {}

    def evaluator(context):
        observed['now'] = context.now
        observed['value'] = context.data.get('value').last_value_number('signal')
        return AlarmEvaluation(
            alarm_identity=context.alarm_identity,
            status=AlarmStatus.ACTIVE,
            evaluated_at=context.now,
            evidence_snapshot=EvidenceSnapshot(
                contract_key='threshold',
                contract_version='1',
                payload={'signal': observed['value']},
            ),
        )

    contract = AlarmEvaluatorContract(
        family_key='mill',
        evaluator_key='threshold',
        evaluator=evaluator,
        inputs=(
            PiInterpolated.latest(
                input_key='value',
                columns=(DataColumn('signal', DataColumnType.FLOAT),),
            ),
        ),
    )
    session = build_alarm_execution_session(
        configuration=_configuration(_plan(identity, evaluator_key='threshold', priority=1)),
        evaluator_registry=AlarmEvaluatorRegistry((contract,)),
    )
    reader = Reader(
        pd.DataFrame(
            {
                'timestamp_utc': [CYCLE_AT],
                'signal': [12.0],
            }
        )
    )

    result = AlarmEvaluationCycle(
        loader=_loader(reader),
        clock=lambda: CYCLE_AT,
    ).run(session)

    assert result.cycle_at == CYCLE_AT
    assert result.evaluations[0].status is AlarmStatus.ACTIVE
    assert observed == {'now': CYCLE_AT, 'value': 12.0}
    assert reader.calls == 1


def test_empty_dataset_reaches_evaluator_for_domain_quality_decision() -> None:
    identity = AlarmIdentity('mill', 'trend')
    called = False

    def evaluator(context):
        nonlocal called
        called = True
        assert context.data.get('history').dataframe.empty
        return AlarmEvaluation(
            alarm_identity=context.alarm_identity,
            status=AlarmStatus.ERROR,
            evaluated_at=context.now,
            error=EvaluationError(
                origin=EvaluationErrorOrigin.QUALITY,
                error_key='insufficient_samples',
                message='Not enough samples for trend evaluation',
            ),
        )

    contract = AlarmEvaluatorContract(
        family_key='mill',
        evaluator_key='trend',
        evaluator=evaluator,
        inputs=(
            PiInterpolated.latest(
                input_key='history',
                columns=(DataColumn('signal', DataColumnType.FLOAT),),
            ),
        ),
    )
    session = build_alarm_execution_session(
        configuration=_configuration(_plan(identity, evaluator_key='trend', priority=1)),
        evaluator_registry=AlarmEvaluatorRegistry((contract,)),
    )

    result = AlarmEvaluationCycle(
        loader=_loader(Reader(None)),
        clock=lambda: CYCLE_AT,
    ).run(session)

    assert called is True
    assert result.evaluations[0].status is AlarmStatus.ERROR
    assert result.evaluations[0].error.origin is EvaluationErrorOrigin.QUALITY
    assert result.evaluations[0].error.error_key == 'insufficient_samples'


def test_technical_input_failure_is_isolated_to_affected_alarm() -> None:
    input_identity = AlarmIdentity('mill', 'input')
    independent_identity = AlarmIdentity('mill', 'independent')
    independent_called = False

    def input_evaluator(context):
        raise AssertionError('input evaluator must not run when source preparation failed')

    def independent_evaluator(context):
        nonlocal independent_called
        independent_called = True
        assert context.data.input_keys == ()
        return AlarmEvaluation(
            alarm_identity=context.alarm_identity,
            status=AlarmStatus.INACTIVE,
            evaluated_at=context.now,
            evidence_snapshot=EvidenceSnapshot(
                contract_key='independent',
                contract_version='1',
                payload={},
            ),
        )

    contracts = (
        AlarmEvaluatorContract(
            family_key='mill',
            evaluator_key='with-input',
            evaluator=input_evaluator,
            inputs=(
                PiInterpolated.latest(
                    input_key='value',
                    columns=(DataColumn('signal', DataColumnType.FLOAT),),
                ),
            ),
        ),
        AlarmEvaluatorContract(
            family_key='mill',
            evaluator_key='independent',
            evaluator=independent_evaluator,
        ),
    )
    session = build_alarm_execution_session(
        configuration=_configuration(
            _plan(input_identity, evaluator_key='with-input', priority=1),
            _plan(independent_identity, evaluator_key='independent', priority=2),
        ),
        evaluator_registry=AlarmEvaluatorRegistry(contracts),
    )

    result = AlarmEvaluationCycle(
        loader=_loader(Reader(fail=True)),
        clock=lambda: CYCLE_AT,
    ).run(session)

    first, second = result.evaluations
    assert first.status is AlarmStatus.ERROR
    assert first.error.origin is EvaluationErrorOrigin.RUNTIME
    assert first.error.error_key == 'input_preparation_failed'
    assert first.error.affected_inputs[0].source_key == 'pi.interpolated'
    assert second.status is AlarmStatus.INACTIVE
    assert independent_called is True


def test_cycle_requires_loader_to_return_the_session_plan() -> None:
    identity = AlarmIdentity('mill', 'risk')
    contract = AlarmEvaluatorContract(
        family_key='mill',
        evaluator_key='threshold',
        evaluator=lambda _context: None,
    )
    session = build_alarm_execution_session(
        configuration=_configuration(_plan(identity, evaluator_key='threshold', priority=1)),
        evaluator_registry=AlarmEvaluatorRegistry((contract,)),
    )

    class InvalidLoader:
        def load(self, *, plan: DataInputLoadPlan, as_of: datetime):
            registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
            other = DataInputLoadPlan(views=(), inputs_by_key={})
            from atlanticus.operational_data.sources import LoadedDataInputs

            return LoadedDataInputs(
                as_of=as_of,
                plan=other,
                registry=registry,
                loaded={},
                failures={},
            )

    try:
        AlarmEvaluationCycle(loader=InvalidLoader(), clock=lambda: CYCLE_AT).run(session)
    except ValueError as error:
        assert 'loaded inputs plan must match' in str(error)
    else:
        raise AssertionError('cycle must reject a loader result for a different plan')
