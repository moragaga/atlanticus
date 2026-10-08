# Diez KPI Latest individuales, separados por fila y posición; no se recupera el JSON Legacy.
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProduccionGlobalRowDefinition:
    key: str
    label: str
    real_key: str
    plan_acumulado_key: str
    proyeccion_key: str
    plan_dia_key: str
    requerido_hora_key: str


PRODUCCION_GLOBAL_DEFINITIONS = (
    ProduccionGlobalRowDefinition(
        key='alimentacion',
        label='Alimentación',
        real_key='alimentacion_chancado_real_inst',
        plan_acumulado_key='alimentacion_chancado_plan_semana_inst',
        proyeccion_key='alimentacion_chancado_proy_inst',
        plan_dia_key='alimentacion_chancado_plan_inst',
        requerido_hora_key='alimentacion_chancado_requerido_plan_inst',
    ),
    ProduccionGlobalRowDefinition(
        key='transportado',
        label='Transportado',
        real_key='transportado_stmg_real_inst',
        plan_acumulado_key='transportado_stmg_plan_semana_inst',
        proyeccion_key='transportado_stmg_proy_inst',
        plan_dia_key='transportado_stmg_plan_inst',
        requerido_hora_key='transportado_stmg_requerido_plan_inst',
    ),
)
