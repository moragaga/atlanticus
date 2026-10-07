from ada.processes.alarm_runtime.session import AlarmEvaluatorRegistry


def build_alarm_evaluator_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=())
