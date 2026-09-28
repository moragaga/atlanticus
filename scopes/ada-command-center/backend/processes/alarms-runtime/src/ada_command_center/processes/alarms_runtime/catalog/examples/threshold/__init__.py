from ada_command_center.processes.alarms_runtime.catalog.examples.threshold.evaluator import (
    evaluate_threshold,
)
from ada_command_center.processes.alarms_runtime.catalog.examples.threshold.requirements import (
    THRESHOLD_REQUIREMENTS,
)
from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorContract


def build_threshold_contract() -> AlarmEvaluatorContract:
    return AlarmEvaluatorContract(
        family_key='mina',
        evaluator_key='threshold',
        evaluator=evaluate_threshold,
        requirements=THRESHOLD_REQUIREMENTS,
    )


__all__ = ['build_threshold_contract']
