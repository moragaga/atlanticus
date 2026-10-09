from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import CorreaStmgDefinition, CorreaStmgMetricDefinition
from .models import CorreasStmgState

_STATES = frozenset({'operando', 'detenido'})


def map_correas_stmg_store(
    store_data: object,
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
    values, source_status = _latest_values(store_data)
    return CorreasStmgState(
        states=tuple(
            _state(values, item.state_kpi_key, source_status) for item in definitions
        ),
        metric=_read(values, metric.value_kpi_key, source_status),
        metric_color=(
            _color(values, metric.color_kpi_key, source_status)
            if metric.color_kpi_key is not None
            else None
        ),
    )


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


def _read(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    value = str(decoded.value).strip()
    return DisplayValue.ok(value) if value else DisplayValue.invalid()


def _state(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    reading = _read(values, key, source_status)
    if reading.status is not DisplayStatus.OK:
        return reading
    state = reading.value.lower()
    return DisplayValue.ok(state) if state in _STATES else DisplayValue.invalid()


def _color(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    reading = _read(values, key, source_status)
    if reading.status is not DisplayStatus.OK:
        return reading
    try:
        return DisplayValue.ok(map_dashboard_value_status(reading.value))
    except ValueError:
        return DisplayValue.invalid()
