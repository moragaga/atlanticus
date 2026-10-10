# El porcentaje se convierte a Decimal y el color se interpreta en el dominio de Feeders.
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.feeder import FeederColor

from .definitions import STOCKPILE_CHACAY_FEEDER_GROUPS, ChacayFeederDefinition
from .models import ChacayFeederReading

_COLOR_CODES = {
    '0': FeederColor.NEUTRAL,
    '1': FeederColor.DANGER,
    '2': FeederColor.WARNING,
}


def map_chacay_feeders_readings(
    readings: Mapping[str, DisplayValue],
    definitions: tuple[tuple[ChacayFeederDefinition, ...], ...] = STOCKPILE_CHACAY_FEEDER_GROUPS,
) -> tuple[tuple[ChacayFeederReading, ...], ...]:
    return tuple(
        tuple(
            ChacayFeederReading(
                value=_numeric(readings[definition.value_kpi_key]),
                color=(
                    _color(readings[definition.color_kpi_key])
                    if definition.color_kpi_key is not None
                    else None
                ),
            )
            for definition in group
        )
        for group in definitions
    )


def _numeric(reading: DisplayValue) -> DisplayValue:
    if reading.status is not DisplayStatus.OK:
        return reading
    try:
        value = Decimal(str(reading.value).strip().replace(',', '.'))
    except InvalidOperation:
        return DisplayValue.invalid()
    if not value.is_finite() or value < 0:
        return DisplayValue.invalid()
    return DisplayValue.ok(value)


def _color(reading: DisplayValue) -> FeederColor | None:
    if reading.status is not DisplayStatus.OK:
        return None
    return _COLOR_CODES.get(str(reading.value).strip())
