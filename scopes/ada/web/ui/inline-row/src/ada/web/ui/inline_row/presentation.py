from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .models import InlineComparisonRowState, InlineValueRowState, InlineValueRowTone


def build_inline_value_row(state: InlineValueRowState) -> Component:
    if not isinstance(state, InlineValueRowState):
        raise TypeError('state must be InlineValueRowState')
    tone_class = (
        ''
        if state.tone is InlineValueRowTone.DEFAULT
        else f'ada-inline-value-row__value--{state.tone.value}'
    )
    border_class = '' if state.show_border else 'ada-inline-value-row--borderless'
    return html.Div(
        className=_classes('ada-inline-value-row', border_class, state.class_name),
        children=[
            html.Div(
                className='ada-inline-value-row__descriptor',
                children=[
                    html.Span(
                        state.definition.label,
                        className=_classes('ada-inline-value-row__label', state.label_class_name),
                    ),
                    (
                        None
                        if state.definition.unit is None
                        else html.Span(
                            f'({state.definition.unit})',
                            className='ada-inline-value-row__unit',
                        )
                    ),
                ],
            ),
            html.Span(
                state.value,
                className=_classes(
                    'ada-inline-value-row__value', tone_class, state.value_class_name
                ),
            ),
        ],
    )


def build_inline_comparison_row(state: InlineComparisonRowState) -> Component:
    if not isinstance(state, InlineComparisonRowState):
        raise TypeError('state must be InlineComparisonRowState')
    border_class = '' if state.show_border else 'ada-inline-comparison-row--borderless'
    return html.Div(
        className=_classes('ada-inline-comparison-row', border_class),
        children=[
            html.Div(
                className='ada-inline-comparison-row__descriptor',
                children=[
                    html.Span(state.definition.label, className='ada-inline-comparison-row__label'),
                    (
                        None
                        if state.definition.unit is None
                        else html.Span(
                            f'({state.definition.unit})',
                            className='ada-inline-comparison-row__unit',
                        )
                    ),
                ],
            ),
            html.Span(
                className='ada-inline-comparison-row__comparison',
                children=[
                    html.Span(
                        state.first_value,
                        className=_comparison_value_class(
                            'ada-inline-comparison-row__first',
                            state.first_tone,
                        ),
                    ),
                    html.Span(
                        state.definition.separator,
                        className='ada-inline-comparison-row__separator',
                    ),
                    html.Span(
                        state.second_value,
                        className=_comparison_value_class(
                            'ada-inline-comparison-row__second',
                            state.second_tone,
                        ),
                    ),
                ],
            ),
        ],
    )


def _comparison_value_class(base: str, tone: InlineValueRowTone) -> str:
    modifier = (
        ''
        if tone is InlineValueRowTone.DEFAULT
        else f'ada-inline-comparison-row__value--{tone.value}'
    )
    return _classes(base, modifier)


def _classes(*values: str | None) -> str:
    return ' '.join(value for value in values if value)
