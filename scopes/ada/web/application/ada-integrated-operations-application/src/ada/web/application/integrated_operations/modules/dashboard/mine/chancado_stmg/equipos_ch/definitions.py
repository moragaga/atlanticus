from __future__ import annotations

from .models import EquiposChDefinition, FeederKpiDefinition

EQUIPOS_CH_DEFINITIONS = (
    EquiposChDefinition(
        key='chancador_1',
        label='CH-1',
        state_kpi_key='chancador_1_estado_inst',
        throughput_kpi_key='chancador_1_tph_inst',
        atollo_kpi_key='chancador_1_atollo_inst',
        atollo_active_value='1',
        atollo_inactive_value='0',
        rendimiento_kpi_key='chancador_1_rendimiento_inst',
        min_atollo_kpi_key='chancador_1_min_atollo_inst',
        min_poste_kpi_key='chancador_1_min_poste_inst',
    ),
    EquiposChDefinition(
        key='chancador_2',
        label='CH-2',
        state_kpi_key='chancador_2_estado_inst',
        throughput_kpi_key='chancador_2_tph_inst',
        atollo_kpi_key='chancador_2_atollo_inst',
        atollo_active_value='1',
        atollo_inactive_value='0',
        rendimiento_kpi_key='chancador_2_rendimiento_inst',
        min_atollo_kpi_key='chancador_2_min_atollo_inst',
        min_poste_kpi_key='chancador_2_min_poste_inst',
    ),
)

FEEDERS_CH_DEFINITIONS = (
    FeederKpiDefinition('feeder_5', '5', 'feeder_5_percent_inst'),
    FeederKpiDefinition('feeder_6', '6', 'feeder_6_percent_inst'),
    FeederKpiDefinition('feeder_7', '7', 'feeder_7_percent_inst'),
    FeederKpiDefinition('feeder_8', '8', 'feeder_8_percent_inst'),
)
