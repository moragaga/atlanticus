# Prepara los tres KPI JSON para todo Carguío con un único acceso a Latest v2.
# Conserva INVALID para los errores del origen según el comportamiento existente.
from __future__ import annotations

from ada.web.kpis.readings import read_component_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .carguio_global_turno.definitions import CARGUIO_GLOBAL_TURNO_KPI_KEY
from .equipos_servicio.definitions import EQUIPOS_SERVICIO_KPI_KEY
from .gestion_carguio_turno.definitions import GESTION_CARGUIO_TURNO_KPI_KEY

_JSON_KEYS = (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    EQUIPOS_SERVICIO_KPI_KEY,
    GESTION_CARGUIO_TURNO_KPI_KEY,
)


def decode_carguio_store(store_data: object) -> dict[str, DisplayValue]:
    readings = read_component_latest(store_data)
    result = {}
    for key in _JSON_KEYS:
        value = readings.json(key)
        result[key] = DisplayValue.invalid() if value.status is DisplayStatus.ERROR else value
    return result
