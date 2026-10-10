from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import PRODUCCION_GLOBAL_DEFINITIONS
from .models import ProduccionGlobalMetric, ProduccionGlobalRow, ProduccionGlobalState


def map_produccion_global_readings(
    readings: Mapping[str, DisplayValue],
) -> ProduccionGlobalState:
    return ProduccionGlobalState(
        rows=tuple(
            ProduccionGlobalRow(
                key=definition.key,
                label=definition.label,
                real=_metric(readings, definition.real_key),
                plan_acumulado=_metric(readings, definition.plan_acumulado_key),
                proyeccion=_metric(readings, definition.proyeccion_key),
                plan_dia=_metric(readings, definition.plan_dia_key),
                requerido_hora=_metric(readings, definition.requerido_hora_key),
            )
            for definition in PRODUCCION_GLOBAL_DEFINITIONS
        )
    )


def _metric(readings: Mapping[str, DisplayValue], kpi_key: str) -> ProduccionGlobalMetric:
    display = readings[kpi_key]
    if display.status is DisplayStatus.OK:
        normalized = display.value.strip()
        display = DisplayValue.ok(normalized) if normalized else DisplayValue.invalid()
    return ProduccionGlobalMetric(kpi_key, display)
