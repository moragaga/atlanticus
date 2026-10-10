# Decodifica los dos KPI JSON una sola vez para todo Transporte Mina.
# Mantiene el estado visual INVALID ante errores de origen del Collector.
from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .numero_operativo_turno.definitions import NUMERO_OPERATIVO_TURNO_KPI_KEY
from .transporte_global_turno.definitions import TRANSPORTE_GLOBAL_TURNO_KPI_KEY

_JSON_KEYS = (TRANSPORTE_GLOBAL_TURNO_KPI_KEY, NUMERO_OPERATIVO_TURNO_KPI_KEY)


def decode_transporte_store(store_data: object) -> dict[str, DisplayValue]:
    readings = read_component_latest(store_data)
    result = {}
    for key in _JSON_KEYS:
        value = readings.json(key)
        result[key] = DisplayValue.invalid() if value.status is DisplayStatus.ERROR else value
    return result
