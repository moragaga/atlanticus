from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .models import EquiposChDefinition, EquiposChReading

_CHANCADOR_STATES = frozenset({'operando', 'detenido', 'mantencion'})


# Se mantiene la validación de claves y la semántica propia de estados, atollo y colores.
def map_equipos_ch_readings(
    readings: Mapping[str, DisplayValue],
    definitions: Sequence[EquiposChDefinition],
) -> tuple[EquiposChReading, ...]:
    if not isinstance(definitions, Sequence) or not all(
        isinstance(item, EquiposChDefinition) for item in definitions
    ):
        raise TypeError('definitions must be a sequence of EquiposChDefinition')
    keys = [
        key
        for definition in definitions
        for key in (
            definition.state_kpi_key,
            definition.throughput_kpi_key,
            definition.atollo_kpi_key,
            definition.rendimiento_kpi_key,
            definition.min_atollo_kpi_key,
            definition.min_poste_kpi_key,
            definition.rendimiento_color_kpi_key,
            definition.min_atollo_color_kpi_key,
            definition.min_poste_color_kpi_key,
        )
    ]
    keys = [key for key in keys if key is not None]
    if len(keys) != len(set(keys)):
        raise ValueError('Equipos CH KPI keys must be globally distinct')

    return tuple(
        EquiposChReading(
            definition=definition,
            state=_state(readings, definition.state_kpi_key),
            throughput=_value(readings, definition.throughput_kpi_key),
            atollo=_atollo(readings, definition),
            rendimiento=_value(readings, definition.rendimiento_kpi_key),
            min_atollo=_value(readings, definition.min_atollo_kpi_key),
            min_poste=_value(readings, definition.min_poste_kpi_key),
            rendimiento_color=_color(readings, definition.rendimiento_color_kpi_key),
            min_atollo_color=_color(readings, definition.min_atollo_color_kpi_key),
            min_poste_color=_color(readings, definition.min_poste_color_kpi_key),
        )
        for definition in definitions
    )


def _value(readings: Mapping[str, DisplayValue], key: str) -> DisplayValue:
    result = readings[key]
    if result.status is not DisplayStatus.OK:
        return result
    normalized = result.value.strip()
    return DisplayValue.ok(normalized) if normalized else DisplayValue.invalid()


# El estado operativo es una regla de dominio del componente, no del decoder genérico.
def _state(readings: Mapping[str, DisplayValue], key: str) -> DisplayValue:
    result = _value(readings, key)
    if result.status is not DisplayStatus.OK:
        return result
    normalized = result.value.lower()
    return (
        DisplayValue.ok(normalized) if normalized in _CHANCADOR_STATES else DisplayValue.invalid()
    )


def _atollo(readings: Mapping[str, DisplayValue], definition: EquiposChDefinition) -> DisplayValue:
    result = _value(readings, definition.atollo_kpi_key)
    if result.status is not DisplayStatus.OK:
        return result
    token = result.value.lower()
    if token == definition.atollo_active_value.strip().lower():
        return DisplayValue.ok(True)
    if token == definition.atollo_inactive_value.strip().lower():
        return DisplayValue.ok(False)
    return DisplayValue.invalid()


# La conversión de códigos de color sigue siendo responsabilidad del componente.
def _color(readings: Mapping[str, DisplayValue], key: str | None) -> DisplayValue | None:
    if key is None:
        return None
    result = _value(readings, key)
    if result.status is not DisplayStatus.OK:
        return result
    try:
        return DisplayValue.ok(map_dashboard_value_status(result.value))
    except ValueError:
        return DisplayValue.invalid()
