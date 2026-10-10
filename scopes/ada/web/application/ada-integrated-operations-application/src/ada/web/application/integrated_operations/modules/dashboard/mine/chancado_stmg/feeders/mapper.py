from __future__ import annotations

from collections.abc import Sequence

from ada.web.kpis.readings import KpiLatestReadings, read_component_latest
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
    keys = [
        key for item in definitions for key in (item.percent_kpi_key, item.color_kpi_key) if key
    ]
    if len(set(keys)) != len(keys):
        raise ValueError('Feeder KPI keys must be globally distinct')
    readings = read_component_latest(store_data)
    return tuple(
        FeederValues(
            percent=_feeder_percent(readings, definition.percent_kpi_key),
            color=(
                _feeder_color(readings, definition.color_kpi_key)
                if definition.color_kpi_key is not None
                else None
            ),
        )
        for definition in definitions
    )


def _feeder_read(readings: KpiLatestReadings, key: str) -> DisplayValue:
    result = readings.scalar(key)
    if result.status is not DisplayStatus.OK:
        return result
    text = result.value.strip()
    return DisplayValue.ok(text) if text else DisplayValue.invalid()


def _feeder_percent(readings: KpiLatestReadings, key: str) -> DisplayValue:
    reading = _feeder_read(readings, key)
    if reading.status is not DisplayStatus.OK:
        return reading
    text = reading.value
    if not text.isascii() or not text.isdecimal():
        return DisplayValue.invalid()
    try:
        return DisplayValue.ok(int(text))
    except ValueError:
        return DisplayValue.invalid()


def _feeder_color(readings: KpiLatestReadings, key: str) -> DisplayValue:
    reading = _feeder_read(readings, key)
    if reading.status is not DisplayStatus.OK:
        return reading
    color = _FEEDER_COLOR_CODES.get(reading.value)
    return DisplayValue.ok(color) if color is not None else DisplayValue.invalid()
