from __future__ import annotations

from math import isfinite

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon

from .models import LevelGaugeView
from .module import ADA_LEVEL_GAUGE_ASSET_LAYER

_TONES = {'default': None, 'warning': '#e0a800', 'danger': '#dc3545'}


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def build_level_gauge(view: LevelGaugeView) -> Component:
    if not isinstance(view, LevelGaugeView):
        raise TypeError('view must be LevelGaugeView')
    level = _percentage(view.level)
    color = _TONES[view.tone] or view.fill_color
    state = _state(view)
    if state.status is DisplayStatus.OK:
        asset = f'/assets/{ADA_LEVEL_GAUGE_ASSET_LAYER.target_name}/img/level/{view.image}/{state.value}.svg'
        picture = html.Div(
            [
                html.Img(src=asset, alt=f'{view.label}: {state.value}', className='ada-level-gauge__image'),
                html.Span(
                    className='ada-level-gauge__column',
                    children=html.Span(
                        className='ada-level-gauge__fill',
                        style={'height': f'{level:g}%', 'backgroundColor': color},
                    ) if level is not None else None,
                ) if level is not None else None,
            ],
            className=f'ada-level-gauge__graphic ada-level-gauge__graphic--{view.image}',
        )
    else:
        picture = _icon(state.status)
    return html.Div(
        [
            html.Div(
                [html.Span(_value(view.level, level)), html.Span(view.unit)],
                className='ada-level-gauge__reading',
            ),
            html.Div(picture, className='ada-level-gauge__illustration'),
            html.Span(view.label, className='ada-level-gauge__label'),
        ],
        className='ada-level-gauge',
    )


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def _percentage(value: DisplayValue) -> float | None:
    if value.status is not DisplayStatus.OK:
        return None
    raw = value.value
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return None
    try:
        number = float(raw)
    except (ValueError, OverflowError):
        return None
    return number if isfinite(number) and 0 <= number <= 100 else None


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def _state(view: LevelGaugeView) -> DisplayValue:
    if view.state_override is not None:
        return DisplayValue.ok(view.state_override)
    if view.state.status is not DisplayStatus.OK:
        return view.state
    if not isinstance(view.state.value, str):
        return DisplayValue.invalid()
    normalized = view.state.value.strip().lower()
    if normalized not in ('operando', 'detenido'):
        return DisplayValue.invalid()
    return DisplayValue.ok(normalized)


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def _value(value: DisplayValue, level: float | None) -> str | Component:
    if level is not None:
        return f'{level:g}'
    return _icon(DisplayStatus.INVALID if value.status is DisplayStatus.OK else value.status)


# Explicación: este bloque implementa la misma responsabilidad que su par productivo.
def _icon(status: DisplayStatus) -> Component:
    visual = build_display_status_icon(status, class_name='ada-level-gauge__status-icon')
    if visual is None:
        raise ValueError('Level gauge display icon cannot be resolved')
    return visual
