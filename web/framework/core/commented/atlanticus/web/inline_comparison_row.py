# Primitiva visual reusable para comparar dos valores en una misma fila.
# No conoce real/plan, KPI, ADA ni collector: el consumidor asigna first/second y sus tonos.
from __future__ import annotations

from dataclasses import dataclass

from dash import html
from dash.development.base_component import Component

from atlanticus.web.inline_value_row import InlineValue, InlineValueRowTone


@dataclass(frozen=True, slots=True)
class InlineComparisonRowDefinition:
    label: str
    unit: str | None = None
    separator: str = '/'

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Inline Comparison Row label cannot be empty')
        if self.unit is not None and (
            not isinstance(self.unit, str) or not self.unit.strip()
        ):
            raise ValueError(
                'Inline Comparison Row unit must be null or a non-empty string'
            )
        if not isinstance(self.separator, str) or not self.separator:
            raise ValueError('Inline Comparison Row separator cannot be empty')


@dataclass(frozen=True, slots=True)
class InlineComparisonRowState:
    definition: InlineComparisonRowDefinition
    first_value: InlineValue
    second_value: InlineValue
    first_tone: InlineValueRowTone = InlineValueRowTone.DEFAULT
    second_tone: InlineValueRowTone = InlineValueRowTone.DEFAULT
    show_border: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.definition, InlineComparisonRowDefinition):
            raise TypeError('definition must be InlineComparisonRowDefinition')
        if not isinstance(self.first_tone, InlineValueRowTone):
            raise TypeError('first_tone must be InlineValueRowTone')
        if not isinstance(self.second_tone, InlineValueRowTone):
            raise TypeError('second_tone must be InlineValueRowTone')
        if not isinstance(self.show_border, bool):
            raise TypeError('show_border must be bool')


def build_inline_comparison_row(
    state: InlineComparisonRowState,
) -> Component:
    if not isinstance(state, InlineComparisonRowState):
        raise TypeError('state must be InlineComparisonRowState')

    # El borde y los tonos son independientes del significado de los valores.
    border_class = (
        ''
        if state.show_border
        else 'atlanticus-inline-comparison-row--borderless'
    )
    return html.Div(
        className=' '.join(
            item
            for item in ('atlanticus-inline-comparison-row', border_class)
            if item
        ),
        children=[
            html.Div(
                className='atlanticus-inline-comparison-row__descriptor',
                children=[
                    html.Span(
                        state.definition.label,
                        className='atlanticus-inline-comparison-row__label',
                    ),
                    (
                        None
                        if state.definition.unit is None
                        else html.Span(
                            f'({state.definition.unit})',
                            className='atlanticus-inline-comparison-row__unit',
                        )
                    ),
                ],
            ),
            html.Span(
                className='atlanticus-inline-comparison-row__comparison',
                children=[
                    html.Span(
                        state.first_value,
                        className=_value_class(
                            'atlanticus-inline-comparison-row__first',
                            state.first_tone,
                        ),
                    ),
                    html.Span(
                        state.definition.separator,
                        className='atlanticus-inline-comparison-row__separator',
                    ),
                    html.Span(
                        state.second_value,
                        className=_value_class(
                            'atlanticus-inline-comparison-row__second',
                            state.second_tone,
                        ),
                    ),
                ],
            ),
        ],
    )


def _value_class(base: str, tone: InlineValueRowTone) -> str:
    modifier = (
        ''
        if tone is InlineValueRowTone.DEFAULT
        else f'atlanticus-inline-comparison-row__value--{tone.value}'
    )
    return ' '.join(item for item in (base, modifier) if item)
