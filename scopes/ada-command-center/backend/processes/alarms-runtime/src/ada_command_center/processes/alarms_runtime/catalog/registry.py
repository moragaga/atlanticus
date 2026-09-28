from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorRegistry


def build_alarm_evaluator_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=())
