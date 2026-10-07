from __future__ import annotations

from ada.alarms.core import (
    AlarmEvaluation,
    AlarmResolutionKey,
    AlarmRouting,
    AlarmStatus,
    EvaluationContext,
    EvidenceSnapshot,
    PlannedAlarm,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality
from ada.processes.alarm_runtime.session import AlarmEvaluatorContract, AlarmEvaluatorRegistry
from atlanticus.operational_data.core import DataColumn, DataColumnType
from atlanticus.operational_data.sources import PiInterpolated


def evaluator(context: EvaluationContext) -> AlarmEvaluation:
    return AlarmEvaluation(
        alarm_identity=context.alarm_identity,
        status=AlarmStatus.INACTIVE,
        evaluated_at=context.now,
        evidence_snapshot=EvidenceSnapshot(
            contract_key='test',
            contract_version='1',
            payload={},
        ),
    )


def engine_configuration(
    *,
    release: str = 'ALARMS-7',
    tool_revision: str = 'TOOLS-4',
    evaluator_key: str = 'threshold',
    limit: float = 10.0,
) -> EngineAlarmConfiguration:
    identity = AlarmIdentity('mill', 'risk')
    plan = PlannedAlarm(
        identity=identity,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        priority_group='mill_feed',
        priority_order=1,
        evaluator_key=evaluator_key,
        alarm_configuration_revision=release,
        tool_registry_revision=tool_revision,
        routing=AlarmRouting(origin_tool_key='tool_a'),
    )
    return EngineAlarmConfiguration(
        resolution_key=AlarmResolutionKey(release, tool_revision),
        defined_alarm_identities=(identity,),
        planned_alarms=(plan,),
        parameters_by_alarm={identity: {'limit': limit}},
    )


def registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(
        contracts=(
            AlarmEvaluatorContract(
                family_key='mill',
                evaluator_key='threshold',
                evaluator=evaluator,
                inputs=(
                    PiInterpolated.latest(
                        input_key='value',
                        columns=(DataColumn('signal', DataColumnType.FLOAT),),
                    ),
                ),
            ),
        )
    )
