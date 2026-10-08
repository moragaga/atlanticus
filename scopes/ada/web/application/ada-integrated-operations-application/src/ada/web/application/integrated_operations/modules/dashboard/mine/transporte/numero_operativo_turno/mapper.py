from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus

from .definitions import (
    NUMERO_OPERATIVO_TURNO_KEYS,
    NUMERO_OPERATIVO_TURNO_KPI_KEY,
)
from .models import NumeroOperativoTurnoState

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_numero_operativo_turno_store(
    store_data: object,
) -> tuple[NumeroOperativoTurnoState | None, DisplayStatus]:
    values, source_status = _latest_values(store_data)
    if values is None:
        return None, source_status

    decoded = decode_kpi_latest_value(
        values.get(NUMERO_OPERATIVO_TURNO_KPI_KEY),
        present=NUMERO_OPERATIVO_TURNO_KPI_KEY in values,
    )
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID

    try:
        return _map_payload(decoded.value), DisplayStatus.OK
    except (TypeError, ValueError):
        return None, DisplayStatus.INVALID


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _map_payload(payload: Mapping[str, object]) -> NumeroOperativoTurnoState:
    if 'data_state' not in payload:
        raise ValueError('Numero Operativo Turno data_state is required')
    data_state = map_dashboard_data_state(payload['data_state'])

    if data_state is DashboardDataState.ERROR:
        return NumeroOperativoTurnoState(values=(), data_state=data_state)

    raw_values = payload.get('values')
    if not isinstance(raw_values, Mapping):
        raise ValueError('Numero Operativo Turno values must be an object')

    if data_state is DashboardDataState.UNSHIFT:
        if raw_values:
            raise ValueError('Numero Operativo Turno unshift values must be empty')
        return NumeroOperativoTurnoState(values=(), data_state=data_state)

    if set(raw_values) != set(NUMERO_OPERATIVO_TURNO_KEYS):
        raise ValueError(
            'Numero Operativo Turno values must contain canonical keys'
        )

    return NumeroOperativoTurnoState(
        values=tuple(
            (key, _require_scalar(raw_values, key))
            for key in NUMERO_OPERATIVO_TURNO_KEYS
        ),
        data_state=data_state,
    )


def _require_scalar(
    values: Mapping[str, object],
    key: str,
) -> str | int | float | bool:
    value = values[key]
    if not isinstance(value, str | int | float | bool):
        raise TypeError(
            f'Numero Operativo Turno value must be a scalar: {key}'
        )
    return value
