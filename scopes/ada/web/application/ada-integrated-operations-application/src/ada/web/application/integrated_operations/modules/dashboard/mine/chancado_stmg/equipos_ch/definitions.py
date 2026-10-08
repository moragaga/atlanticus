from __future__ import annotations

from .models import EquiposChDefinition


EQUIPOS_CH_DEFINITIONS = (
    EquiposChDefinition(
        key='chancador_1',
        label='CH-1',
        state_kpi_key='chancador_1_estado_inst',
        throughput_kpi_key='chancador_1_tph_inst',
        atollo_kpi_key='chancador_1_atollo_inst',
        atollo_active_value='1',
        atollo_inactive_value='0',
    ),
    EquiposChDefinition(
        key='chancador_2',
        label='CH-2',
        state_kpi_key='chancador_2_estado_inst',
        throughput_kpi_key='chancador_2_tph_inst',
        atollo_kpi_key='chancador_2_atollo_inst',
        atollo_active_value='1',
        atollo_inactive_value='0',
    ),
)
