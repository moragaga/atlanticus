from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dash import html
from dash.development.base_component import Component

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    build_inline_value_row,
)


@dataclass(frozen=True, slots=True)
class FluidMetricDefinition:
    label: str
    kpi_key: str
    unit: str


@dataclass(frozen=True, slots=True)
class FluidMetricReading:
    definition: FluidMetricDefinition
    value: DisplayValue


def latest_values(store_data: object) -> tuple[Mapping[str, object] | None, DisplayStatus]:
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


def display_value(
    values: Mapping[str, object] | None, key: str, source_status: DisplayStatus
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
    raw = str(decoded.value).strip()
    return DisplayValue.ok(raw) if raw else DisplayValue.invalid()


def map_metrics(
    store_data: object, definitions: Sequence[FluidMetricDefinition]
) -> tuple[FluidMetricReading, ...]:
    values, status = latest_values(store_data)
    return tuple(FluidMetricReading(d, display_value(values, d.kpi_key, status)) for d in definitions)


def build_metric_rows(readings: Sequence[FluidMetricReading], *, class_name: str) -> Component:
    return html.Div(
        [
            html.Div(
                build_inline_value_row(
                    InlineValueRowState(
                        InlineValueRowDefinition(item.definition.label, unit=item.definition.unit),
                        display_value_component(item.value),
                    )
                ),
                role='button',
                tabIndex=0,
                title=item.definition.kpi_key,
                **{'data-kpi-inspection-key': item.definition.kpi_key},
            )
            for item in readings
        ],
        className=class_name,
    )


def display_value_component(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        return str(value.value)
    icon = build_display_status_icon(value.status)
    if icon is None:
        raise ValueError('Fluid metric icon cannot be resolved')
    return icon
