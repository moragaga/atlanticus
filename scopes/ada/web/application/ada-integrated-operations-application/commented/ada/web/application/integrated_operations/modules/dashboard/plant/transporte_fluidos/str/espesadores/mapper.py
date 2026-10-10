from __future__ import annotations

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from ada.web.kpis.readings import (
    read_component_latest,
)
from .definitions import STR_ESPESADORES
from .models import StrEspesadorReading, StrMetricReading


# Los estados y métricas de espesadores usan lecturas textuales independientes.
def map_str_espesadores_store(store_data: object) -> tuple[StrEspesadorReading, ...]:
    source = read_component_latest(store_data)
    return tuple(
        StrEspesadorReading(
            definition=definition,
            state=source.text(definition.state_kpi_key),
            feed=_feed(source.text(definition.feed_kpi_key)),
            metrics=tuple(
                StrMetricReading(metric, source.text(metric.kpi_key))
                for metric in definition.metrics
            ),
        )
        for definition in STR_ESPESADORES
    )


# No se transforma un KPI ausente o erróneo en un equipo detenido.
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
