from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.feeder import FeederColor

from .definitions import STOCKPILE_CHACAY_FEEDER_GROUPS, ChacayFeederDefinition
from .models import ChacayFeederReading

_COLOR_CODES = {
    '0': FeederColor.NEUTRAL,
    '1': FeederColor.DANGER,
    '2': FeederColor.WARNING,
}


# Se usa el store latest actual; no se aceptan ni adaptan documentos JSON legacy.
def map_chacay_feeders_store(
    store_data: object,
    definitions: tuple[tuple[ChacayFeederDefinition, ...], ...] = STOCKPILE_CHACAY_FEEDER_GROUPS,
) -> tuple[tuple[ChacayFeederReading, ...], ...]:
    values, source_status = _latest_values(store_data)
    return tuple(
        tuple(
            ChacayFeederReading(
                value=_numeric(values, definition.value_kpi_key, source_status),
                color=_color(values, definition.color_kpi_key, source_status),
            )
            for definition in group
        )
        for group in definitions
    )


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _read(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if not isinstance(decoded.value, str | int | float):
        return DisplayValue.invalid()
    return DisplayValue.ok(decoded.value)


# Un cero es un valor válido. Los decimales y enteros se preservan sin crear un estado active.
def _numeric(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    reading = _read(values, key, source_status)
    if reading.status is not DisplayStatus.OK:
        return reading
    try:
        value = Decimal(str(reading.value).strip().replace(',', '.'))
    except InvalidOperation:
        return DisplayValue.invalid()
    if not value.is_finite() or value < 0:
        return DisplayValue.invalid()
    return DisplayValue.ok(value)


# El color opcional interpreta los mismos códigos del feeder ya existente; si falta, es neutro.
def _color(
    values: Mapping[str, object] | None,
    key: str | None,
    source_status: DisplayStatus,
) -> FeederColor | None:
    if key is None:
        return None
    reading = _read(values, key, source_status)
    if reading.status is not DisplayStatus.OK:
        return None
    return _COLOR_CODES.get(str(reading.value).strip())
