# El registro agrega contratos completos exportados por cada lógica.
# No repite columnas, particiones ni parámetros; no crea estado global compartido.

from ada_command_center.processes.alarms_runtime.catalog.mina.threshold import (
    build_threshold_contract,
)
from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorRegistry


# La composición productiva puede recibir este registro sin alterar el Engine.
def build_alarm_evaluator_registry() -> AlarmEvaluatorRegistry:
    return AlarmEvaluatorRegistry(contracts=(build_threshold_contract(),))
