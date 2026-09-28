from ada_command_center.processes.alarms_runtime.catalog.mina.threshold import (
    build_threshold_contract,
)
from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorRegistry


def build_alarm_evaluator_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=(build_threshold_contract(),))
