from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import STR_ESPESADORES
from .models import StrEspesadorReading, StrMetricReading


def map_str_espesadores_readings(
    readings: Mapping[str, DisplayValue]
) -> tuple[StrEspesadorReading, ...]:
    return tuple(
        StrEspesadorReading(
            definition=definition,
            state=readings[definition.state_kpi_key],
            feed=_feed(readings[definition.feed_kpi_key]),
            metrics=tuple(
                StrMetricReading(metric, readings[metric.kpi_key]) for metric in definition.metrics
            ),
        )
        for definition in STR_ESPESADORES
    )


def _feed(value: DisplayValue) -> DisplayValue:
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
