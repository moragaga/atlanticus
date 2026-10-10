from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .models import (
    MOVIMIENTO_MINA_KPI_KEY,
    MOVIMIENTO_MINA_ROW_KEYS,
    MovimientoMinaComparison,
    MovimientoMinaRow,
    MovimientoMinaRowKey,
    MovimientoMinaState,
)

_UNAVAILABLE_STATES = {
    DisplayStatus.NOT_MAPPED: KpiLatestValueState.NOT_MAPPED,
    DisplayStatus.EMPTY: KpiLatestValueState.MISSING,
    DisplayStatus.ERROR: KpiLatestValueState.ERROR,
}


class MovimientoMinaContractError(ValueError):
    pass


class MovimientoMinaUnavailableError(MovimientoMinaContractError):
    def __init__(self, state: KpiLatestValueState) -> None:
        if state not in {
            KpiLatestValueState.NOT_MAPPED,
            KpiLatestValueState.MISSING,
            KpiLatestValueState.ERROR,
        }:
            raise ValueError('Unavailable state must be not_mapped, missing or error')
        self.state = state
        super().__init__(f'Movimiento Mina latest value is unavailable: {state.value}')


def map_movimiento_mina_readings(readings: Mapping[str, DisplayValue]) -> MovimientoMinaState:
    result = readings[MOVIMIENTO_MINA_KPI_KEY]
    if result.status in _UNAVAILABLE_STATES:
        raise MovimientoMinaUnavailableError(_UNAVAILABLE_STATES[result.status])
    if result.status is not DisplayStatus.OK:
        raise MovimientoMinaContractError(
            f'Movimiento Mina latest value is invalid: {result.status.value}'
        )
    if not isinstance(result.value, Mapping):
        raise MovimientoMinaContractError('Movimiento Mina latest value must be a JSON object')
    return map_movimiento_mina_payload(result.value)


def map_movimiento_mina_payload(payload: Mapping[str, object]) -> MovimientoMinaState:
    if 'data_state' not in payload:
        raise MovimientoMinaContractError('Movimiento Mina data_state is required')
    try:
        data_state = map_dashboard_data_state(payload['data_state'])
    except ValueError as error:
        raise MovimientoMinaContractError(str(error)) from error
    if data_state is DashboardDataState.ERROR and 'rows' not in payload:
        return MovimientoMinaState(rows=(), data_state=data_state)
    rows = _require_mapping(payload, 'rows')
    return MovimientoMinaState(
        rows=tuple(_map_row(rows, key) for key in MOVIMIENTO_MINA_ROW_KEYS),
        data_state=data_state,
    )


def _map_row(rows: Mapping[str, object], key: MovimientoMinaRowKey) -> MovimientoMinaRow:
    row = _require_mapping(rows, key.value)
    return MovimientoMinaRow(
        key=key,
        avance=_map_comparison(row, section_key='avance', value_key='real'),
        cierre=_map_comparison(row, section_key='cierre', value_key='proyeccion'),
        ritmo=_require_value(_require_mapping(row, 'ritmo'), 'requerido'),
    )


def _map_comparison(
    row: Mapping[str, object],
    *,
    section_key: str,
    value_key: str,
) -> MovimientoMinaComparison:
    section = _require_mapping(row, section_key)
    try:
        status = map_dashboard_value_status(section.get('status'))
    except ValueError as error:
        raise MovimientoMinaContractError(str(error)) from error
    return MovimientoMinaComparison(
        value=_require_value(section, value_key),
        plan=_require_value(section, 'plan'),
        status=status,
    )


def _require_mapping(container: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise MovimientoMinaContractError(f'Movimiento Mina field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise MovimientoMinaContractError(f'Movimiento Mina field is required: {key}')
    return container[key]
