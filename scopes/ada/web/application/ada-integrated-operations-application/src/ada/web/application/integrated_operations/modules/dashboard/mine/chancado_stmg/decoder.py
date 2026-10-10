from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayValue

from .correas_stmg import CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC
from .equipos_ch import EQUIPOS_CH_DEFINITIONS
from .feeders import FEEDERS_CH_DEFINITIONS
from .leyes import LEYES_DEFINITIONS
from .produccion_global import PRODUCCION_GLOBAL_DEFINITIONS
from .stockpile import STOCKPILE_MINA_KPI_KEYS

_TEXT_KEYS = tuple(
    dict.fromkeys(
        (
            *(
                key
                for item in PRODUCCION_GLOBAL_DEFINITIONS
                for key in (
                    item.real_key,
                    item.plan_acumulado_key,
                    item.proyeccion_key,
                    item.plan_dia_key,
                    item.requerido_hora_key,
                )
            ),
            *(
                key
                for item in EQUIPOS_CH_DEFINITIONS
                for key in (
                    item.state_kpi_key,
                    item.throughput_kpi_key,
                    item.atollo_kpi_key,
                    item.rendimiento_kpi_key,
                    item.min_atollo_kpi_key,
                    item.min_poste_kpi_key,
                    item.rendimiento_color_kpi_key,
                    item.min_atollo_color_kpi_key,
                    item.min_poste_color_kpi_key,
                )
                if key is not None
            ),
            *(
                key
                for _, percent_key, height_key in STOCKPILE_MINA_KPI_KEYS
                for key in (percent_key, height_key)
            ),
            *(item.state_kpi_key for item in CORREAS_STMG_DEFINITIONS),
            CORREAS_STMG_METRIC.value_kpi_key,
            *(
                (CORREAS_STMG_METRIC.color_kpi_key,)
                if CORREAS_STMG_METRIC.color_kpi_key is not None
                else ()
            ),
            *(
                key
                for item in LEYES_DEFINITIONS
                for key in (item.hora_key, item.turno_key, item.dia_key, item.plan_key)
            ),
        )
    )
)

_SCALAR_KEYS = tuple(
    dict.fromkeys(
        key
        for item in FEEDERS_CH_DEFINITIONS
        for key in (item.percent_kpi_key, item.color_kpi_key)
        if key is not None
    )
)


def decode_chancado_stmg_store(store_data: object) -> dict[str, DisplayValue]:
    readings = read_component_latest(store_data)
    values = {key: readings.text(key) for key in _TEXT_KEYS}
    values.update({key: readings.scalar(key) for key in _SCALAR_KEYS})
    return values
