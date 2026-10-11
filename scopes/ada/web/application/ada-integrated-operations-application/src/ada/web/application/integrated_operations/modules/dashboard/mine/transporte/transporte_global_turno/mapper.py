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

from .definitions import (
    TRANSPORTE_GLOBAL_TURNO_KPI_KEY,
    TRANSPORTE_GLOBAL_TURNO_ROW_KEYS,
)
from .models import (
    TransporteGlobalTurnoRow,
    TransporteGlobalTurnoState,
    TransporteGlobalTurnoValue,
)


def map_transporte_global_turno_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[TransporteGlobalTurnoState | None, DisplayStatus]:
    reading = readings[TRANSPORTE_GLOBAL_TURNO_KPI_KEY]
    if reading.status is not DisplayStatus.OK:
        return None, reading.status
    if not isinstance(reading.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_payload(reading.value), DisplayStatus.OK
    except TypeError, ValueError:
        return None, DisplayStatus.INVALID


def _map_payload(payload: Mapping[str, object]) -> TransporteGlobalTurnoState:
    if 'data_state' not in payload:
        raise ValueError('Transporte Global Turno data_state is required')
    data_state = map_kpi_payload_data_state(payload['data_state'])

    if data_state is KpiPayloadDataState.ERROR:
        return TransporteGlobalTurnoState(rows=(), data_state=data_state)

    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Transporte Global Turno rows must be a JSON array')
    if data_state is KpiPayloadDataState.UNSHIFT:
        if rows:
            raise ValueError('Transporte Global Turno unshift rows must be empty')
        return TransporteGlobalTurnoState(rows=(), data_state=data_state)

    mapped = tuple(_map_row(item) for item in rows)
    row_by_key = {row.key: row for row in mapped}
    if len(row_by_key) != len(mapped):
        raise ValueError('Transporte Global Turno row keys must be unique')
    if set(row_by_key) != set(TRANSPORTE_GLOBAL_TURNO_ROW_KEYS):
        raise ValueError('Transporte Global Turno rows must contain canonical keys')

    return TransporteGlobalTurnoState(
        rows=tuple(row_by_key[key] for key in TRANSPORTE_GLOBAL_TURNO_ROW_KEYS),
        data_state=data_state,
    )


def _map_row(value: object) -> TransporteGlobalTurnoRow:
    if not isinstance(value, Mapping):
        raise ValueError('Transporte Global Turno row must be an object')

    key = _require_value(value, 'key')
    if not isinstance(key, str) or not key.strip():
        raise ValueError('Transporte Global Turno key must be non-empty')

    return TransporteGlobalTurnoRow(
        key=key,
        real=_map_value(_require_mapping(value, 'real')),
        plan=_map_value(_require_mapping(value, 'plan')),
    )


def _map_value(value: Mapping[str, object]) -> TransporteGlobalTurnoValue:
    metric_value = _require_value(value, 'value')
    if not isinstance(metric_value, str | int | float | bool):
        raise TypeError('Transporte Global Turno metric value must be a scalar')
    if 'status' not in value:
        raise ValueError('Transporte Global Turno metric status is required')
    return TransporteGlobalTurnoValue(
        value=metric_value,
        status=map_value_severity_code(value['status']),
    )


def _require_mapping(
    container: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f'Transporte Global Turno field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Transporte Global Turno field is required: {key}')
    return container[key]
