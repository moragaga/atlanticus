from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .models import (
    StockpileDefinition,
    StockpileValues,
    StockpileVariant,
    validate_stockpile_values,
)
from .svg import StockpileRenderValues, build_stockpile_data_uri
from .values import StockpileReading, resolve_stockpile_reading

_NO_INFORMATION = 'Sin información'


def build_stockpile_component(
    definition: StockpileDefinition,
    values: StockpileValues,
    *,
    component_id: str | None = None,
    class_name: str | None = None,
    alt: str = 'Stockpile',
) -> Component:
    validate_stockpile_values(definition, values)
    percentage = resolve_stockpile_reading(values.percent, percentage=True)
    height = (
        resolve_stockpile_reading(values.height_m, percentage=False)
        if definition.variant is StockpileVariant.VARIABLE_HEIGHT
        else None
    )
    failure = _failure_status(percentage, height)
    if failure is not None:
        icon = build_display_status_icon(failure, class_name='ada-stockpile__status-icon')
        if icon is None:
            raise ValueError('Stockpile error icon cannot be resolved')
        return html.Span(
            icon,
            className=_classes('ada-stockpile__error', class_name),
            **({'id': component_id} if component_id is not None else {}),
        )

    rendered = _resolve_render_values(definition, percentage, height)
    style = {'display': 'block', 'width': '100%', 'height': 'auto', 'objectFit': 'contain'}
    if definition.max_width_px is not None:
        style['maxWidth'] = f'{definition.max_width_px}px'
    if definition.max_height_px is not None:
        style['maxHeight'] = f'{definition.max_height_px}px'
    return html.Img(
        src=build_stockpile_data_uri(definition, rendered),
        alt=alt,
        draggable=False,
        style=style,
        className=_classes('ada-stockpile__graphic', class_name),
        **({'id': component_id} if component_id is not None else {}),
    )


def _failure_status(
    percentage: StockpileReading, height: StockpileReading | None
) -> DisplayStatus | None:
    statuses = (percentage.status, height.status if height is not None else None)
    if DisplayStatus.ERROR in statuses:
        return DisplayStatus.ERROR
    if DisplayStatus.INVALID in statuses:
        return DisplayStatus.INVALID
    return None


def _resolve_render_values(
    definition: StockpileDefinition,
    percentage: StockpileReading,
    height: StockpileReading | None,
) -> StockpileRenderValues:
    has_percentage = percentage.status is DisplayStatus.OK
    has_height = height is not None and height.status is DisplayStatus.OK
    missing_both = (
        definition.variant is StockpileVariant.VARIABLE_HEIGHT
        and not has_height
        and not has_percentage
    )
    height_ratio = 1.0
    height_text = None
    if definition.variant is StockpileVariant.VARIABLE_HEIGHT:
        if has_height:
            height_ratio = min(height.number / definition.scale_max_m, 1.0)
            height_text = f'{height.text}m'
        else:
            height_ratio = 1.0 if missing_both else 0.0
    show_fill = has_percentage and (
        has_height or definition.variant is StockpileVariant.FIXED_PROFILE
    )
    return StockpileRenderValues(
        percent=percentage.number if show_fill else 0.0,
        height_ratio=height_ratio,
        percent_text=f'{percentage.text}%' if has_percentage else _NO_INFORMATION,
        height_text=height_text,
    )


def _classes(base: str, extra: str | None) -> str:
    return ' '.join(part for part in (base, extra) if part)
