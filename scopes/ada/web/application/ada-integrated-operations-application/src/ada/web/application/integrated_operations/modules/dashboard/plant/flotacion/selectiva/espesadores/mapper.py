from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import ESPESADORES, EspesadorDefinition
from .models import EspesadorMetricReading, EspesadorReading


def map_espesadores_readings(
    readings: Mapping[str, DisplayValue],
) -> tuple[EspesadorReading, ...]:
    return tuple(_espesador(definition, readings) for definition in ESPESADORES)


def _espesador(
    definition: EspesadorDefinition, readings: Mapping[str, DisplayValue]
) -> EspesadorReading:
    feed_value = readings[definition.feed_kpi_key]
    return EspesadorReading(
        definition=definition,
        state=readings[definition.state_kpi_key],
        feed=_feed_state(feed_value),
        metrics=tuple(
            EspesadorMetricReading(item, readings[item.kpi_key]) for item in definition.metrics
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
