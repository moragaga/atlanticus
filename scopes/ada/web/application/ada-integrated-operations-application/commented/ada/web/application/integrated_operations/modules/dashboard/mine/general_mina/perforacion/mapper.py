# El resumen y el detalle JSON comparten el mismo diccionario preparado.
# Los porcentajes y las filas se validan aquí porque pertenecen al dominio.
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import TypeVar

from ada.web.kpis.readings import (
    KpiPayloadDataState,
    map_kpi_payload_data_state,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    map_value_severity_code,
)

from .definitions import PERFORACION_DETALLE_KPI_KEY, PERFORACION_RESUMEN_KPI_KEY
from .models import (
    PerforacionComparison,
    PerforacionDetalleState,
    PerforacionEquipoState,
    PerforacionFaseState,
    PerforacionResumenState,
    PerforacionState,
)

_PERCENTAGE_PATTERN = re.compile(r'^(?:100(?:\.0+)?|(?:\d{1,2})(?:\.\d+)?)%$')
_T = TypeVar('_T')


def map_perforacion_readings(readings: Mapping[str, DisplayValue]) -> PerforacionState:
    resumen, resumen_status = _map_json_value(
        readings[PERFORACION_RESUMEN_KPI_KEY], _map_resumen_payload
    )
    detalle, detalle_status = _map_json_value(
        readings[PERFORACION_DETALLE_KPI_KEY], _map_detalle_payload
    )
    return PerforacionState(
        resumen=resumen,
        resumen_status=resumen_status,
        detalle=detalle,
        detalle_status=detalle_status,
    )


def _map_json_value(
    reading: DisplayValue,
    payload_mapper: Callable[[Mapping[str, object]], _T],
) -> tuple[_T | None, DisplayStatus]:
    if reading.status is not DisplayStatus.OK:
        status = DisplayStatus.INVALID if reading.status is DisplayStatus.ERROR else reading.status
        return None, status
    if not isinstance(reading.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return payload_mapper(reading.value), DisplayStatus.OK
    except ValueError:
        return None, DisplayStatus.INVALID


def _map_resumen_payload(payload: Mapping[str, object]) -> PerforacionResumenState:
    data_state = _map_data_state(payload)
    if data_state is KpiPayloadDataState.ERROR:
        return PerforacionResumenState(data_state=data_state)
    acumulado_semanal = _map_comparison(_require_mapping(payload, 'acumulado_semanal'))
    plan_semanal = _require_value(payload, 'plan_semanal')
    avance = _require_value(payload, 'avance')
    if avance is not None:
        if not isinstance(avance, str) or _PERCENTAGE_PATTERN.fullmatch(avance) is None:
            raise ValueError('Perforacion resumen avance must be a percentage string')
    if data_state is KpiPayloadDataState.OK and avance is None:
        raise ValueError('Perforacion resumen avance is required when data_state is ok')
    return PerforacionResumenState(
        data_state=data_state,
        acumulado_semanal=acumulado_semanal,
        plan_semanal=plan_semanal,
        avance=avance,
    )


def _map_detalle_payload(payload: Mapping[str, object]) -> PerforacionDetalleState:
    data_state = _map_data_state(payload)
    if data_state is KpiPayloadDataState.ERROR:
        return PerforacionDetalleState(data_state=data_state, fases=())
    fases = payload.get('fases')
    if not isinstance(fases, list):
        raise ValueError('Perforacion detalle fases must be a JSON array')
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
    return PerforacionEquipoState(
        perforadora=_require_value(value, 'perforadora'),
        dia_anterior=_map_comparison(_require_mapping(value, 'dia_anterior')),
        acumulado_semanal=_map_comparison(_require_mapping(value, 'acumulado_semanal')),
    )


def _map_comparison(value: Mapping[str, object]) -> PerforacionComparison:
    try:
        status = map_value_severity_code(value.get('status'))
    except ValueError as error:
        raise ValueError(str(error)) from error
    return PerforacionComparison(
        real=_require_value(value, 'real'),
        plan=_require_value(value, 'plan'),
        status=status,
    )


def _map_data_state(payload: Mapping[str, object]) -> KpiPayloadDataState:
    if 'data_state' not in payload:
        raise ValueError('Perforacion data_state is required')
    try:
        return map_kpi_payload_data_state(payload['data_state'])
    except ValueError as error:
        raise ValueError(str(error)) from error


def _require_mapping(container: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f'Perforacion field must be an object: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Perforacion field is required: {key}')
    return container[key]
