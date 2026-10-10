# Este es el único punto del componente que conoce la lectura de Latest v2.
# Se resuelven las siete claves consumidas por las tarjetas, una vez por actualización.
from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayValue

from .movimiento_mina.models import MOVIMIENTO_MINA_KPI_KEY
from .mp10.definitions import MP10_HOTEL_MINA_INST_KPI_KEY, MP10_HOTEL_MINA_PROY_KPI_KEY
from .perforacion.definitions import PERFORACION_DETALLE_KPI_KEY, PERFORACION_RESUMEN_KPI_KEY
from .remanentes.definitions import REMANENTES_SUMMARY_KPI_KEY, STOCK_3080_KPI_KEY

_JSON_KEYS = (
    MOVIMIENTO_MINA_KPI_KEY,
    REMANENTES_SUMMARY_KPI_KEY,
    PERFORACION_RESUMEN_KPI_KEY,
    PERFORACION_DETALLE_KPI_KEY,
    MP10_HOTEL_MINA_INST_KPI_KEY,
    MP10_HOTEL_MINA_PROY_KPI_KEY,
)


def decode_general_mina_store(store_data: object) -> dict[str, DisplayValue]:
    readings = read_component_latest(store_data)
    values = {key: readings.json(key) for key in _JSON_KEYS}
    values[STOCK_3080_KPI_KEY] = readings.text(STOCK_3080_KPI_KEY)
    return values
