from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import ESPESADORES, EspesadorDefinition
from .models import EspesadorMetricReading, EspesadorReading


def map_espesadores_store(store_data: object) -> tuple[EspesadorReading, ...]:
    values, status = _latest_values(store_data)
    return tuple(_espesador(definition, values, status) for definition in ESPESADORES)


def _espesador(
    definition: EspesadorDefinition,
    values: Mapping[str, object] | None,
    status: DisplayStatus,
) -> EspesadorReading:
    feed_value = _value(values, definition.feed_kpi_key, status)
    return EspesadorReading(
        definition=definition,
        state=_value(values, definition.state_kpi_key, status),
        feed=_feed_state(feed_value),
        metrics=tuple(
            EspesadorMetricReading(item, _value(values, item.kpi_key, status))
            for item in definition.metrics
        ),
    )


def _feed_state(value: DisplayValue) -> DisplayValue:
    if value.status is not DisplayStatus.OK:
        return value
    if not isinstance(value.value, str):
        return DisplayValue.invalid()
    state = value.value.strip().casefold()
    if state == 'alimentando':
        return DisplayValue.ok('operando')
    if state in {'no alimentando', 'detenido'}:
        return DisplayValue.ok('detenido')
    return DisplayValue.invalid()


def _latest_values(store_data: object) -> tuple[Mapping[str, object] | None, DisplayStatus]:
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


def _value(
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
    raw = str(decoded.value).strip()
    return DisplayValue.ok(raw) if raw else DisplayValue.invalid()
