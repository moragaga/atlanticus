from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus

from .definitions import EQUIPOS_SERVICIO_KPI_KEY
from .models import (
    EquiposServicioComparison,
    EquiposServicioRow,
    EquiposServicioState,
)

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_equipos_servicio_store(
    store_data: object,
) -> tuple[EquiposServicioState | None, DisplayStatus]:
    values, source_status = _latest_values(store_data)
    if values is None:
        return None, source_status

    decoded = decode_kpi_latest_value(
        values.get(EQUIPOS_SERVICIO_KPI_KEY),
        present=EQUIPOS_SERVICIO_KPI_KEY in values,
    )
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID

    try:
        return _map_payload(decoded.value), DisplayStatus.OK
    except TypeError, ValueError:
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


def _map_payload(payload: Mapping[str, object]) -> EquiposServicioState:
    if 'data_state' not in payload:
        raise ValueError('Equipos Servicio data_state is required')
    data_state = map_dashboard_data_state(payload['data_state'])

    if data_state is DashboardDataState.ERROR:
        return EquiposServicioState(rows=(), data_state=data_state)

    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Equipos Servicio rows must be a JSON array')

    return EquiposServicioState(
        rows=tuple(_map_row(item) for item in rows),
        data_state=data_state,
    )


def _map_row(value: object) -> EquiposServicioRow:
    if not isinstance(value, Mapping):
        raise ValueError('Equipos Servicio row must be an object')

    equipo = _require_value(value, 'equipo')
    if not isinstance(equipo, str) or not equipo.strip():
        raise ValueError('Equipos Servicio equipo must be a non-empty string')

    is_total = _require_value(value, 'is_total')
    if not isinstance(is_total, bool):
        raise TypeError('Equipos Servicio is_total must be bool')

    return EquiposServicioRow(
        equipo=equipo,
        is_total=is_total,
        operando=_map_comparison(_require_mapping(value, 'operando')),
        disponibles=_map_comparison(_require_mapping(value, 'disponibles')),
        fuera_servicio=_map_comparison(_require_mapping(value, 'fuera_servicio')),
    )


def _map_comparison(
    value: Mapping[str, object],
) -> EquiposServicioComparison:
    real = _require_value(value, 'real')
    plan = _require_value(value, 'plan')
    if not isinstance(real, str | int | float | bool):
        raise TypeError('Equipos Servicio real must be a scalar')
    if not isinstance(plan, str | int | float | bool):
        raise TypeError('Equipos Servicio plan must be a scalar')

    if 'status' not in value:
        raise ValueError('Equipos Servicio status is required')

    return EquiposServicioComparison(
        real=real,
        plan=plan,
        status=map_dashboard_value_status(value['status']),
    )


def _require_mapping(
    container: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f'Equipos Servicio field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Equipos Servicio field is required: {key}')
    return container[key]
