# Adapta los dos KPI JSON de Perforación desde el Component KPI Store sin lógica de negocio.
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import TypeVar

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus

from .definitions import PERFORACION_DETALLE_KPI_KEY, PERFORACION_RESUMEN_KPI_KEY
from .models import (
    PerforacionComparison,
    PerforacionDetalleState,
    PerforacionEquipoState,
    PerforacionFaseState,
    PerforacionResumenState,
    PerforacionState,
)

# La Web valida que avance sea CSS-ready, pero no convierte ni recalcula el porcentaje.
_PERCENTAGE_PATTERN = re.compile(r'^(?:100(?:\.0+)?|(?:\d{1,2})(?:\.\d+)?)%$')
_T = TypeVar('_T')

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_perforacion_store(store_data: object) -> PerforacionState:
    values, source_status = _latest_values(store_data)
    # Resumen y detalle se decodifican por separado para que puedan degradarse independientemente.
    resumen, resumen_status = _map_json_value(
        values,
        source_status=source_status,
        kpi_key=PERFORACION_RESUMEN_KPI_KEY,
        payload_mapper=_map_resumen_payload,
    )
    detalle, detalle_status = _map_json_value(
        values,
        source_status=source_status,
        kpi_key=PERFORACION_DETALLE_KPI_KEY,
        payload_mapper=_map_detalle_payload,
    )
    return PerforacionState(
        resumen=resumen,
        resumen_status=resumen_status,
        detalle=detalle,
        detalle_status=detalle_status,
    )


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


def _map_json_value(
    values: Mapping[str, object] | None,
    *,
    source_status: DisplayStatus,
    kpi_key: str,
    payload_mapper: Callable[[Mapping[str, object]], _T],
) -> tuple[_T | None, DisplayStatus]:
    if values is None:
        return None, source_status
    decoded = decode_kpi_latest_value(
        values.get(kpi_key),
        present=kpi_key in values,
    )
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return payload_mapper(decoded.value), DisplayStatus.OK
    except ValueError:
        return None, DisplayStatus.INVALID


def _map_resumen_payload(payload: Mapping[str, object]) -> PerforacionResumenState:
    data_state = _map_data_state(payload)
    # ERROR no obliga al backend a fabricar métricas.
    if data_state is DashboardDataState.ERROR:
        return PerforacionResumenState(data_state=data_state)
    acumulado_semanal = _map_comparison(
        _require_mapping(payload, 'acumulado_semanal')
    )
    plan_semanal = _require_value(payload, 'plan_semanal')
    avance = _require_value(payload, 'avance')
    if avance is not None:
        if not isinstance(avance, str) or _PERCENTAGE_PATTERN.fullmatch(avance) is None:
            raise ValueError('Perforacion resumen avance must be a percentage string')
    if data_state is DashboardDataState.OK and avance is None:
        raise ValueError('Perforacion resumen avance is required when data_state is ok')
    return PerforacionResumenState(
        data_state=data_state,
        acumulado_semanal=acumulado_semanal,
        plan_semanal=plan_semanal,
        avance=avance,
    )


def _map_detalle_payload(payload: Mapping[str, object]) -> PerforacionDetalleState:
    data_state = _map_data_state(payload)
    if data_state is DashboardDataState.ERROR:
        return PerforacionDetalleState(data_state=data_state, fases=())
    fases = payload.get('fases')
    if not isinstance(fases, list):
        raise ValueError('Perforacion detalle fases must be a JSON array')
    # No hay sorting ni filtrado: backend define fases, equipos, orden y cardinalidad.
    return PerforacionDetalleState(
        data_state=data_state,
        fases=tuple(_map_fase(item) for item in fases),
    )


def _map_fase(value: object) -> PerforacionFaseState:
    if not isinstance(value, Mapping):
        raise ValueError('Perforacion fase must be an object')
    perforadoras = value.get('perforadoras')
    if not isinstance(perforadoras, list):
        raise ValueError('Perforacion fase perforadoras must be a JSON array')
    return PerforacionFaseState(
        fase=_require_value(value, 'fase'),
        perforadoras=tuple(_map_equipo(item) for item in perforadoras),
    )


def _map_equipo(value: object) -> PerforacionEquipoState:
    if not isinstance(value, Mapping):
        raise ValueError('Perforacion perforadora must be an object')
    # PFAR/PF123 ya debe venir normalizado desde backend.
    return PerforacionEquipoState(
        perforadora=_require_value(value, 'perforadora'),
        dia_anterior=_map_comparison(_require_mapping(value, 'dia_anterior')),
        acumulado_semanal=_map_comparison(
            _require_mapping(value, 'acumulado_semanal')
        ),
    )


def _map_comparison(value: Mapping[str, object]) -> PerforacionComparison:
    try:
        status = map_dashboard_value_status(value.get('status'))
    except ValueError as error:
        raise ValueError(str(error)) from error
    return PerforacionComparison(
        real=_require_value(value, 'real'),
        plan=_require_value(value, 'plan'),
        status=status,
    )


def _map_data_state(payload: Mapping[str, object]) -> DashboardDataState:
    if 'data_state' not in payload:
        raise ValueError('Perforacion data_state is required')
    try:
        return map_dashboard_data_state(payload['data_state'])
    except ValueError as error:
        raise ValueError(str(error)) from error


def _require_mapping(
    container: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f'Perforacion field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Perforacion field is required: {key}')
    return container[key]
