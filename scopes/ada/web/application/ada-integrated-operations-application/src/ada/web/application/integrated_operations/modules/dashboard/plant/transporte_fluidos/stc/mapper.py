from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView

from ..indicators import FluidMetricReading, map_metrics
from .definitions import STC_ESPESADOR, STC_INDICATORS, STC_LEVELS, StcLevelDefinition
from .models import StcEspesadorReading, StcReading


def map_stc_readings(readings: Mapping[str, DisplayValue]) -> StcReading:
    feed = readings[STC_ESPESADOR.feed_key]
    espesador = StcEspesadorReading(
        definition=STC_ESPESADOR,
        state=readings[STC_ESPESADOR.state_key],
        feed=_feed_state(feed),
        metrics=tuple(
            FluidMetricReading(definition, readings[definition.kpi_key])
            for definition in STC_ESPESADOR.metrics
        ),
    )
    return StcReading(
        indicators=map_metrics(readings, STC_INDICATORS),
        espesador=espesador,
        levels=tuple(_level(readings, definition) for definition in STC_LEVELS),
    )


def _feed_state(value: DisplayValue) -> DisplayValue:
    if value.status is not DisplayStatus.OK:
        return value
    if not isinstance(value.value, str):
        return DisplayValue.invalid()
    normalized = value.value.strip().casefold()
    if normalized == 'alimentando':
        return DisplayValue.ok('operando')
    if normalized in ('no alimentando', 'detenido'):
        return DisplayValue.ok('detenido')
    return DisplayValue.invalid()


def _level(readings: Mapping[str, DisplayValue], definition: StcLevelDefinition) -> LevelGaugeView:
    tone = 'default'
    if definition.color_key is not None:
        color_value = readings[definition.color_key]
        if color_value.status is DisplayStatus.OK:
            tone = {'1': 'danger', '2': 'warning'}.get(str(color_value.value), 'default')
    state = (
        readings[definition.state_key]
        if definition.state_key is not None
        else DisplayValue.not_mapped()
    )
    return LevelGaugeView(
        label=definition.label,
        image=definition.image,
        level=readings[definition.level_key],
        state=state,
        state_override=definition.state_override,
        fill_color=definition.fill_color,
        tone=tone,
    )
