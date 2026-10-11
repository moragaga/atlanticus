# Solo interpreta el JSON de flotas y sus comparaciones; no conoce Latest v2.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.readings import (
    KpiPayloadDataState,
    map_kpi_payload_data_state,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    map_value_severity_code,
)

from .definitions import CARGUIO_GLOBAL_TURNO_KPI_KEY
from .models import (
    CarguioGlobalTurnoComparison,
    CarguioGlobalTurnoRow,
    CarguioGlobalTurnoState,
)


def map_carguio_global_turno_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[CarguioGlobalTurnoState | None, DisplayStatus]:
    reading = readings[CARGUIO_GLOBAL_TURNO_KPI_KEY]
    if reading.status is not DisplayStatus.OK:
        return None, reading.status
    if not isinstance(reading.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_payload(reading.value), DisplayStatus.OK
    except TypeError, ValueError:
        return None, DisplayStatus.INVALID


def _map_payload(payload: Mapping[str, object]) -> CarguioGlobalTurnoState:
    if 'data_state' not in payload:
        raise ValueError('Carguio Global Turno data_state is required')
    data_state = map_kpi_payload_data_state(payload['data_state'])

    if data_state is KpiPayloadDataState.ERROR:
        return CarguioGlobalTurnoState(rows=(), data_state=data_state)

    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Carguio Global Turno rows must be a JSON array')

    return CarguioGlobalTurnoState(
        rows=tuple(_map_row(item) for item in rows),
        data_state=data_state,
    )


def _map_row(value: object) -> CarguioGlobalTurnoRow:
    if not isinstance(value, Mapping):
        raise ValueError('Carguio Global Turno row must be an object')

    flota = _require_value(value, 'flota')
    if not isinstance(flota, str) or not flota.strip():
        raise ValueError('Carguio Global Turno flota must be a non-empty string')

    is_total = _require_value(value, 'is_total')
    if not isinstance(is_total, bool):
        raise TypeError('Carguio Global Turno is_total must be bool')

    return CarguioGlobalTurnoRow(
        flota=flota,
        is_total=is_total,
        op_req=_map_comparison(_require_mapping(value, 'op_req')),
        disponibilidad=_map_comparison(_require_mapping(value, 'disponibilidad')),
        uebd=_map_comparison(_require_mapping(value, 'uebd')),
        rendimiento=_map_comparison(_require_mapping(value, 'rendimiento')),
    )


def _map_comparison(
    value: Mapping[str, object],
) -> CarguioGlobalTurnoComparison:
    real = _require_value(value, 'real')
    plan = _require_value(value, 'plan')
    if not isinstance(real, str | int | float | bool):
        raise TypeError('Carguio Global Turno real must be a scalar')
    if not isinstance(plan, str | int | float | bool):
        raise TypeError('Carguio Global Turno plan must be a scalar')

    if 'status' not in value:
        raise ValueError('Carguio Global Turno status is required')
    status = map_value_severity_code(value['status'])

    return CarguioGlobalTurnoComparison(
        real=real,
        plan=plan,
        status=status,
    )


def _require_mapping(
    container: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f'Carguio Global Turno field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Carguio Global Turno field is required: {key}')
    return container[key]
