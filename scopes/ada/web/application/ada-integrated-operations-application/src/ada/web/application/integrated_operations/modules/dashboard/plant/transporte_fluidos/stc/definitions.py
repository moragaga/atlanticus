from __future__ import annotations

from dataclasses import dataclass

from ..metrics import FluidMetricDefinition


@dataclass(frozen=True, slots=True)
class StcEspesadorDefinition:
    label: str
    state_key: str
    feed_key: str
    metrics: tuple[FluidMetricDefinition, ...]


@dataclass(frozen=True, slots=True)
class StcLevelDefinition:
    label: str
    level_key: str
    state_key: str | None
    color_key: str | None
    image: str = 'tk'
    state_override: str | None = None
    fill_color: str = '#5b5c64'


STC_INDICATORS = (
    FluidMetricDefinition('Concentrado', 'concentrado_entregado_puerto_real_mean_hora', 't/h'),
    FluidMetricDefinition('Sólido Puerto', 'solido_puerto_real_mean_hora', '%'),
    FluidMetricDefinition('Malla +100', 'malla_100_real', '%'),
)

STC_ESPESADOR = StcEspesadorDefinition(
    label='TK-711',
    state_key='estado_tk_711_inst',
    feed_key='estado_alimentacion_tk_711_inst',
    metrics=(
        FluidMetricDefinition('Altura', 'altura_tk_711_inst', '%'),
        FluidMetricDefinition('Torque', 'torque_tk_711_inst', '%'),
        FluidMetricDefinition('Flujo', 'flujo_tk_711_inst', 't/h'),
        FluidMetricDefinition('Sólido', 'solido_tk_711_inst', '%'),
    ),
)

STC_LEVELS = (
    StcLevelDefinition('TK-20', 'nivel_tk_020_inst', 'estado_tk_020_inst', 'tk20_nivel_color'),
    StcLevelDefinition('TK-21', 'nivel_tk_021_inst', 'estado_tk_021_inst', 'tk21_nivel_color'),
)
