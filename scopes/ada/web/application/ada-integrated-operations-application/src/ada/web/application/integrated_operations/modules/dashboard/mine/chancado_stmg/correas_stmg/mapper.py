from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import CorreaStmgDefinition, CorreaStmgMetricDefinition
from .models import CorreasStmgState

_STATES = frozenset({'operando', 'detenido'})


def map_correas_stmg_readings(
    readings: Mapping[str, DisplayValue],
    definitions: Sequence[CorreaStmgDefinition],
    metric: CorreaStmgMetricDefinition,
) -> CorreasStmgState:
    if not isinstance(definitions, Sequence) or not all(
        isinstance(item, CorreaStmgDefinition) for item in definitions
    ):
        raise TypeError('definitions must be a sequence of CorreaStmgDefinition')
    if not isinstance(metric, CorreaStmgMetricDefinition):
        raise TypeError('metric must be CorreaStmgMetricDefinition')
    keys = [*(item.state_kpi_key for item in definitions), metric.value_kpi_key]
    if metric.color_kpi_key is not None:
        keys.append(metric.color_kpi_key)
    if len(keys) != len(set(keys)):
        raise ValueError('Correa STMG KPI keys must be distinct')
    return CorreasStmgState(
        states=tuple(_state(readings, item.state_kpi_key) for item in definitions),
        metric=_read(readings, metric.value_kpi_key),
        metric_color=(
            _color(readings, metric.color_kpi_key) if metric.color_kpi_key is not None else None
        ),
    )


def _read(readings: Mapping[str, DisplayValue], key: str) -> DisplayValue:
    result = readings[key]
    if result.status is not DisplayStatus.OK:
        return result
    normalized = result.value.strip()
    return DisplayValue.ok(normalized) if normalized else DisplayValue.invalid()


def _state(readings: Mapping[str, DisplayValue], key: str) -> DisplayValue:
    reading = _read(readings, key)
    if reading.status is not DisplayStatus.OK:
        return reading
    state = reading.value.lower()
    return DisplayValue.ok(state) if state in _STATES else DisplayValue.invalid()


def _color(readings: Mapping[str, DisplayValue], key: str) -> DisplayValue:
    reading = _read(readings, key)
    if reading.status is not DisplayStatus.OK:
        return reading
    try:
        return DisplayValue.ok(map_dashboard_value_status(reading.value))
    except ValueError:
        return DisplayValue.invalid()
