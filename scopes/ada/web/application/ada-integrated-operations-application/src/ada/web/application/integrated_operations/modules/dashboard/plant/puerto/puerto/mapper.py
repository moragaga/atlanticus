from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView
from ada.web.ui.time_series import TimeSeriesValues

from .definitions import FILTERS, FILTRADO_ACCUMULATED, FILTRADO_TREND, SHIPMENT, TANKS
from .models import FilterReading, PuertoReading


def map_puerto_readings(
    readings: Mapping[str, DisplayValue], histories: Mapping[str, TimeSeriesValues]
) -> PuertoReading:
    duration, unit = _duration(readings[SHIPMENT.duration_key])
    return PuertoReading(
        trend_current=readings[FILTRADO_TREND.kpi_key],
        trend_history=histories[FILTRADO_TREND.kpi_key],
        accumulated=readings[FILTRADO_ACCUMULATED.kpi_key],
        tanks=tuple(_tank(item, readings) for item in TANKS),
        filters=tuple(
            FilterReading(item, _operational(readings[item.state_key])) for item in FILTERS
        ),
        tonnage=readings[SHIPMENT.tonnage.kpi_key],
        duration=duration,
        duration_unit=unit,
        ship_state=_operational(readings[SHIPMENT.state_key]),
    )


def _tank(definition, readings: Mapping[str, DisplayValue]) -> LevelGaugeView:
    color = readings[definition.color_key]
    tone = (
        {'1': 'danger', '2': 'warning'}.get(str(color.value), 'default')
        if color.status is DisplayStatus.OK
        else 'default'
    )
    return LevelGaugeView(
        label=definition.label,
        image='tk',
        level=readings[definition.level_key],
        state=DisplayValue.ok('operando'),
        state_override='operando',
        tone=tone,
    )


def _operational(value: DisplayValue) -> DisplayValue:
    if value.status is not DisplayStatus.OK:
        return value
    state = value.value.strip().lower() if isinstance(value.value, str) else ''
    return DisplayValue.ok(state) if state in {'operando', 'detenido'} else DisplayValue.invalid()


def _duration(value: DisplayValue) -> tuple[DisplayValue, str]:
    if value.status is not DisplayStatus.OK:
        return value, ''
    try:
        if isinstance(value.value, bool):
            raise ValueError('Invalid duration value')
        seconds = float(value.value)
        if not isfinite(seconds):
            raise ValueError('Invalid duration value')
        seconds = max(0, int(seconds))
    except (TypeError, ValueError, OverflowError):
        return DisplayValue.invalid(), ''
    if seconds == 0:
        return DisplayValue.ok('0'), ''
    if seconds < 60:
        return DisplayValue.ok(str(seconds)), 's'
    if seconds < 3600:
        return DisplayValue.ok(str(seconds // 60)), 'm'
    if seconds < 86400:
        return DisplayValue.ok(f'>{seconds // 3600}'), 'h'
    return DisplayValue.ok(f'>{seconds // 86400}'), 'd'
