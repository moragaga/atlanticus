# Adapta el único KPI JSON de Carguío Global • Turno sin cálculos de negocio.
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

from .definitions import CARGUIO_GLOBAL_TURNO_KPI_KEY
from .models import (
    CarguioGlobalTurnoComparison,
    CarguioGlobalTurnoRow,
    CarguioGlobalTurnoState,
)

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_carguio_global_turno_store(
    store_data: object,
) -> tuple[CarguioGlobalTurnoState | None, DisplayStatus]:
    values, source_status = _latest_values(store_data)
    if values is None:
        return None, source_status

    decoded = decode_kpi_latest_value(
        values.get(CARGUIO_GLOBAL_TURNO_KPI_KEY),
        present=CARGUIO_GLOBAL_TURNO_KPI_KEY in values,
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
        return None, DisplayStatus.EMPTY
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _map_payload(payload: Mapping[str, object]) -> CarguioGlobalTurnoState:
    if 'data_state' not in payload:
        raise ValueError('Carguio Global Turno data_state is required')
    data_state = map_dashboard_data_state(payload['data_state'])

    # ERROR puede omitir completamente la tabla.
    if data_state is DashboardDataState.ERROR:
        return CarguioGlobalTurnoState(rows=(), data_state=data_state)

    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Carguio Global Turno rows must be a JSON array')

    # No hay sorting, sumatorias ni construcción de TOTAL en Web.
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

    # La semántica TOTAL viene explícita desde backend y no se infiere desde flota.
    is_total = _require_value(value, 'is_total')
    if not isinstance(is_total, bool):
        raise TypeError('Carguio Global Turno is_total must be bool')

    return CarguioGlobalTurnoRow(
        flota=flota,
        is_total=is_total,
        op_req=_map_comparison(_require_mapping(value, 'op_req')),
        disponibilidad=_map_comparison(
            _require_mapping(value, 'disponibilidad')
        ),
        uebd=_map_comparison(_require_mapping(value, 'uebd')),
        rendimiento=_map_comparison(_require_mapping(value, 'rendimiento')),
    )


def _map_comparison(
    value: Mapping[str, object],
) -> CarguioGlobalTurnoComparison:
    # real y plan se preservan como escalares opacos; Web sólo interpreta status.
    real = _require_value(value, 'real')
    plan = _require_value(value, 'plan')
    if not isinstance(real, str | int | float | bool):
        raise TypeError('Carguio Global Turno real must be a scalar')
    if not isinstance(plan, str | int | float | bool):
        raise TypeError('Carguio Global Turno plan must be a scalar')

    if 'status' not in value:
        raise ValueError('Carguio Global Turno status is required')
    status = map_dashboard_value_status(value['status'])

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
