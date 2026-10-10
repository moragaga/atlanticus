from __future__ import annotations

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .._latest import display_value, latest_values
from .definitions import STR_ESPESADORES
from .models import StrEspesadorReading, StrMetricReading


def map_str_espesadores_store(store_data: object) -> tuple[StrEspesadorReading, ...]:
    values, status = latest_values(store_data)
    return tuple(
        StrEspesadorReading(
            definition=definition,
            state=display_value(values, definition.state_kpi_key, status),
            feed=_feed(display_value(values, definition.feed_kpi_key, status)),
            metrics=tuple(
                StrMetricReading(metric, display_value(values, metric.kpi_key, status))
                for metric in definition.metrics
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
