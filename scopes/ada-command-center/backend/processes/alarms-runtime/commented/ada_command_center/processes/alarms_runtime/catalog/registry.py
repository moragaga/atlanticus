# Registro productivo: incorpora solamente contratos de lógicas aprobadas.
# Los ejemplos permanecen explícitamente fuera de esta composición.

from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorRegistry


# Se agregan implementaciones reales cuando estén disponibles y calificadas.
def build_alarm_evaluator_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=())
