from __future__ import annotations

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.level_gauge import LevelGaugeView

from ..metrics import FluidMetricReading, display_value, latest_values, map_metrics
from .definitions import STC_ESPESADOR, STC_INDICATORS, STC_LEVELS, StcLevelDefinition
from .models import StcEspesadorReading, StcReading


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def map_stc_store(store_data: object) -> StcReading:
    values, status = latest_values(store_data)
    feed = display_value(values, STC_ESPESADOR.feed_key, status)
    espesador = StcEspesadorReading(
        definition=STC_ESPESADOR,
        state=display_value(values, STC_ESPESADOR.state_key, status),
        feed=_feed_state(feed),
        metrics=tuple(
            FluidMetricReading(definition, display_value(values, definition.kpi_key, status))
            for definition in STC_ESPESADOR.metrics
        ),
    )
    return StcReading(
        indicators=map_metrics(store_data, STC_INDICATORS),
        espesador=espesador,
        levels=tuple(_level(values, status, definition) for definition in STC_LEVELS),
    )


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
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


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def _level(values, status: DisplayStatus, definition: StcLevelDefinition) -> LevelGaugeView:
    tone = 'default'
    if definition.color_key is not None:
        color_value = display_value(values, definition.color_key, status)
        if color_value.status is DisplayStatus.OK:
            tone = {'1': 'danger', '2': 'warning'}.get(str(color_value.value), 'default')
    state = (
        display_value(values, definition.state_key, status)
        if definition.state_key is not None
        else DisplayValue.not_mapped()
    )
    return LevelGaugeView(
        label=definition.label,
        image=definition.image,
        level=display_value(values, definition.level_key, status),
        state=state,
        state_override=definition.state_override,
        fill_color=definition.fill_color,
        tone=tone,
    )
