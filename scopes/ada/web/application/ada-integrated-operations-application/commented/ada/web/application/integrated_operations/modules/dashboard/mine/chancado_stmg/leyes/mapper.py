from __future__ import annotations

from collections.abc import Mapping

from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import LEYES_DEFINITIONS
from .models import LeyesMetric, LeyesRow, LeyesState


# Leyes conserva su forma de tabla; solo consume valores preparados de Latest v2.
def map_leyes_readings(readings: Mapping[str, DisplayValue]) -> LeyesState:
    return LeyesState(
        rows=tuple(
            LeyesRow(
                key=definition.key,
                label=definition.label,
                hora=_metric(readings, definition.hora_key),
                turno=_metric(readings, definition.turno_key),
                dia=_metric(readings, definition.dia_key),
                plan=_metric(readings, definition.plan_key),
            )
            for definition in LEYES_DEFINITIONS
        )
    )


# Solo aplicamos la normalización de presentación específica de este mapper.
def _metric(readings: Mapping[str, DisplayValue], kpi_key: str) -> LeyesMetric:
    display = readings[kpi_key]
    if display.status is DisplayStatus.OK and not display.value.strip():
        display = DisplayValue.invalid()
    return LeyesMetric(kpi_key, display)
