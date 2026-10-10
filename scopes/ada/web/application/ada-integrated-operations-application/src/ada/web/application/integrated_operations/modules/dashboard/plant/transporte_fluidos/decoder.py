from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayValue

from .sta.definitions import STA_INDICATORS
from .stc.definitions import STC_ESPESADOR, STC_INDICATORS, STC_LEVELS
from .str.ductos.definitions import DUCTOS
from .str.espesadores.definitions import STR_ESPESADORES
from .str.overview.definitions import STR_TREND
from .tranque.definitions import TRANQUE_INDICATORS

_KEYS = tuple(
    dict.fromkeys(
        (
            STR_TREND.kpi_key,
            *(
                key
                for tank in STR_ESPESADORES
                for key in (
                    tank.state_kpi_key,
                    tank.feed_kpi_key,
                    *(metric.kpi_key for metric in tank.metrics),
                )
            ),
            *(
                key
                for duct in DUCTOS
                for key in (
                    duct.state_kpi_key,
                    duct.solids_in_kpi_key,
                    duct.solids_out_kpi_key,
                    *(pump.state_kpi_key for pump in duct.pumps),
                )
            ),
            *(metric.kpi_key for metric in STC_INDICATORS),
            STC_ESPESADOR.state_key,
            STC_ESPESADOR.feed_key,
            *(metric.kpi_key for metric in STC_ESPESADOR.metrics),
            *(
                key
                for level in STC_LEVELS
                for key in (level.level_key, level.state_key, level.color_key)
            ),
            *(metric.kpi_key for metric in TRANQUE_INDICATORS),
            *(metric.kpi_key for metric in STA_INDICATORS),
        )
    )
)
_KEYS = tuple(key for key in _KEYS if key is not None)
_SCALAR_KEYS = frozenset(level.level_key for level in STC_LEVELS)


def decode_transporte_fluidos_store(store_data: object) -> dict[str, DisplayValue]:
    latest = read_component_latest(store_data)
    return {
        key: latest.scalar(key) if key in _SCALAR_KEYS else latest.text(key)
        for key in _KEYS
    }
