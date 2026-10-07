from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value

from .models import (
    MOVIMIENTO_MINA_KPI_KEY,
    MOVIMIENTO_MINA_ROW_KEYS,
    MovimientoMinaComparison,
    MovimientoMinaDataState,
    MovimientoMinaMetricStatus,
    MovimientoMinaRow,
    MovimientoMinaState,
)


class MovimientoMinaContractError(ValueError):
    pass


class MovimientoMinaUnavailableError(MovimientoMinaContractError):
    # Separa ausencia operacional de KPI de una violación estructural del JSON.
    def __init__(self, state: KpiLatestValueState) -> None:
        if state not in {
            KpiLatestValueState.NOT_MAPPED,
            KpiLatestValueState.MISSING,
            KpiLatestValueState.ERROR,
        }:
            raise ValueError('Unavailable state must be not_mapped, missing or error')
        self.state = state
        super().__init__(f'Movimiento Mina latest value is unavailable: {state.value}')


def map_movimiento_mina_store(store_data: object) -> MovimientoMinaState:
    values = _latest_values(store_data)
    present = MOVIMIENTO_MINA_KPI_KEY in values
    decoded = decode_kpi_latest_value(
        values.get(MOVIMIENTO_MINA_KPI_KEY),
        present=present,
    )
    # KPI no mapeado, faltante o con error de fuente es disponibilidad, no contrato JSON inválido.
    if decoded.state in {
        KpiLatestValueState.NOT_MAPPED,
        KpiLatestValueState.MISSING,
        KpiLatestValueState.ERROR,
    }:
        raise MovimientoMinaUnavailableError(decoded.state)
    if decoded.state is not KpiLatestValueState.OK:
        raise MovimientoMinaContractError(
            f'Movimiento Mina latest value is invalid: {decoded.state.value}'
        )
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        raise MovimientoMinaContractError('Movimiento Mina latest value must be a JSON object')
    return map_movimiento_mina_payload(decoded.value)


def map_movimiento_mina_payload(payload: Mapping[str, object]) -> MovimientoMinaState:
    rows = _require_mapping(payload, 'rows')
    return MovimientoMinaState(
        rows=tuple(_map_row(rows, key.value) for key in MOVIMIENTO_MINA_ROW_KEYS),
        data_state=_map_data_state(payload.get('data_state')),
    )


def _latest_values(store_data: object) -> Mapping[str, object]:
    if not isinstance(store_data, Mapping):
        raise MovimientoMinaContractError('General Mina store must be an object')
    latest = store_data.get('latest')
    # Un Component KPI Store válido con latest=None representa collector/delivery todavía sin datos, no un contrato roto.
    if latest is None:
        raise MovimientoMinaUnavailableError(KpiLatestValueState.MISSING)
    if not isinstance(latest, Mapping):
        raise MovimientoMinaContractError('General Mina store latest payload must be an object')
    values = latest.get('values')
    if not isinstance(values, Mapping):
        raise MovimientoMinaContractError('General Mina latest values must be an object')
    return values


def _map_row(rows: Mapping[str, object], key: str) -> MovimientoMinaRow:
    row = _require_mapping(rows, key)
    return MovimientoMinaRow(
        key=next(item for item in MOVIMIENTO_MINA_ROW_KEYS if item.value == key),
        avance=_map_comparison(row, section_key='avance', value_key='real'),
        cierre=_map_comparison(row, section_key='cierre', value_key='proyeccion'),
        # Ritmo también se conserva opaco; el mapper sólo exige presencia estructural.
        ritmo=_require_value(_require_mapping(row, 'ritmo'), 'requerido'),
    )


def _map_comparison(
    row: Mapping[str, object],
    *,
    section_key: str,
    value_key: str,
) -> MovimientoMinaComparison:
    section = _require_mapping(row, section_key)
    return MovimientoMinaComparison(
        # real/proyección y plan no se convierten, limpian ni formatean en Web.
        value=_require_value(section, value_key),
        plan=_require_value(section, 'plan'),
        status=_map_status(section.get('status')),
    )


def _map_status(value: object) -> MovimientoMinaMetricStatus:
    if value is None:
        return MovimientoMinaMetricStatus.NEUTRAL
    if type(value) is not int:
        raise MovimientoMinaContractError('Movimiento Mina status must be 0, 1, 2 or null')
    if value == 0:
        return MovimientoMinaMetricStatus.NEUTRAL
    if value == 1:
        return MovimientoMinaMetricStatus.DANGER
    if value == 2:
        return MovimientoMinaMetricStatus.WARNING
    raise MovimientoMinaContractError('Movimiento Mina status must be 0, 1, 2 or null')


def _map_data_state(value: object) -> MovimientoMinaDataState:
    if value is None:
        return MovimientoMinaDataState.READY
    if value == 'unshift':
        return MovimientoMinaDataState.UNSHIFT
    if value == 'error':
        return MovimientoMinaDataState.ERROR
    raise MovimientoMinaContractError('Movimiento Mina data_state must be null, unshift or error')


def _require_mapping(container: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise MovimientoMinaContractError(f'Movimiento Mina field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise MovimientoMinaContractError(f'Movimiento Mina field is required: {key}')
    return container[key]
