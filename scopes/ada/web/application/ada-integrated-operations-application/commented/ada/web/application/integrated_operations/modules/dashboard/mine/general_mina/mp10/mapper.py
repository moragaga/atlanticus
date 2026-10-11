# Ambos KPI JSON ya fueron preparados; solo se interpreta cada métrica de MP10.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    map_value_severity_code,
)

from .definitions import MP10_HOTEL_MINA_INST_KPI_KEY, MP10_HOTEL_MINA_PROY_KPI_KEY
from .models import MP10MetricState, MP10State


def map_mp10_readings(readings: Mapping[str, DisplayValue]) -> MP10State:
    instant, instant_status = _map_metric(readings[MP10_HOTEL_MINA_INST_KPI_KEY])
    projection, projection_status = _map_metric(readings[MP10_HOTEL_MINA_PROY_KPI_KEY])
    return MP10State(
        instant=instant,
        instant_status=instant_status,
        projection=projection,
        projection_status=projection_status,
    )


def _map_metric(reading: DisplayValue) -> tuple[MP10MetricState | None, DisplayStatus]:
    if reading.status is not DisplayStatus.OK:
        status = DisplayStatus.INVALID if reading.status is DisplayStatus.ERROR else reading.status
        return None, status
    if not isinstance(reading.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_metric_payload(reading.value), DisplayStatus.OK
    except TypeError, ValueError:
        return None, DisplayStatus.INVALID


def _map_metric_payload(payload: Mapping[str, object]) -> MP10MetricState:
    value = _require_value(payload, 'value')
    if not isinstance(value, str | int | float | bool):
        raise TypeError('MP10 value must be a scalar')

    if 'alert' not in payload:
        raise ValueError('MP10 alert is required')
    alert = payload['alert']
    if alert is not None and (not isinstance(alert, str) or not alert.strip()):
        raise ValueError('MP10 alert must be null or a non-empty string')

    if 'status' not in payload:
        raise ValueError('MP10 status is required')
    status = map_value_severity_code(payload['status'])

    return MP10MetricState(
        value=value,
        alert=alert,
        status=status,
    )


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'MP10 field is required: {key}')
    return container[key]
