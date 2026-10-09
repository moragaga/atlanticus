from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.feeder import FeederColor, FeederValues

from .models import FeederKpiDefinition

_FEEDER_COLOR_CODES = {
    '0': FeederColor.NEUTRAL,
    '1': FeederColor.DANGER,
    '2': FeederColor.WARNING,
}


def map_feeders_store(
    store_data: object,
    definitions: Sequence[FeederKpiDefinition],
) -> tuple[FeederValues, ...]:
    if not isinstance(definitions, Sequence) or not all(
        isinstance(item, FeederKpiDefinition) for item in definitions
    ):
        raise TypeError('definitions must be a sequence of FeederKpiDefinition')
    keys = [key for item in definitions for key in (item.percent_kpi_key, item.color_kpi_key) if key]
    if len(set(keys)) != len(keys):
        raise ValueError('Feeder KPI keys must be globally distinct')
    values, status = _latest_values(store_data)
    return tuple(
        FeederValues(
            percent=_feeder_percent(values, definition.percent_kpi_key, status),
            color=(
                _feeder_color(values, definition.color_kpi_key, status)
                if definition.color_kpi_key is not None else None
            ),
        )
        for definition in definitions
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


def _feeder_read(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(status)
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
    if type(decoded.value) is int:
        return DisplayValue.ok(decoded.value)
    if not isinstance(decoded.value, str):
        return DisplayValue.invalid()
    text = decoded.value.strip()
    return DisplayValue.ok(text) if text else DisplayValue.invalid()


def _feeder_percent(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    reading = _feeder_read(values, key, status)
    if reading.status is not DisplayStatus.OK:
        return reading
    text = reading.value
    if type(text) is int:
        return DisplayValue.ok(text) if text >= 0 else DisplayValue.invalid()
    if not text.isascii() or not text.isdecimal():
        return DisplayValue.invalid()
    try:
        return DisplayValue.ok(int(text))
    except ValueError:
        return DisplayValue.invalid()


def _feeder_color(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    reading = _feeder_read(values, key, status)
    if reading.status is not DisplayStatus.OK:
        return reading
    color = _FEEDER_COLOR_CODES.get(str(reading.value))
    return DisplayValue.ok(color) if color is not None else DisplayValue.invalid()
