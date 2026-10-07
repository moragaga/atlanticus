from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from dash import html
from dash.development.base_component import Component

InlineValue: TypeAlias = str | int | float | bool | Component | None


class InlineValueRowTone(StrEnum):
    DEFAULT = 'default'
    DANGER = 'danger'
    WARNING = 'warning'


@dataclass(frozen=True, slots=True)
class InlineValueRowDefinition:
    label: str
    unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Inline Value Row label cannot be empty')
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit.strip()):
            raise ValueError('Inline Value Row unit must be null or a non-empty string')


@dataclass(frozen=True, slots=True)
class InlineValueRowState:
    definition: InlineValueRowDefinition
    value: InlineValue
    tone: InlineValueRowTone = InlineValueRowTone.DEFAULT
    show_border: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.definition, InlineValueRowDefinition):
            raise TypeError('definition must be InlineValueRowDefinition')
        if not isinstance(self.tone, InlineValueRowTone):
            raise TypeError('tone must be InlineValueRowTone')
        if not isinstance(self.show_border, bool):
            raise TypeError('show_border must be bool')


def build_inline_value_row(state: InlineValueRowState) -> Component:
    if not isinstance(state, InlineValueRowState):
        raise TypeError('state must be InlineValueRowState')
    tone_class = (
        ''
        if state.tone is InlineValueRowTone.DEFAULT
        else f'atlanticus-inline-value-row__value--{state.tone.value}'
    )
    border_class = '' if state.show_border else 'atlanticus-inline-value-row--borderless'
    return html.Div(
        className=' '.join(
            item for item in ('atlanticus-inline-value-row', border_class) if item
        ),
        children=[
            html.Div(
                className='atlanticus-inline-value-row__descriptor',
                children=[
                    html.Span(
                        state.definition.label,
                        className='atlanticus-inline-value-row__label',
                    ),
                    (
                        None
                        if state.definition.unit is None
                        else html.Span(
                            f'({state.definition.unit})',
                            className='atlanticus-inline-value-row__unit',
                        )
                    ),
                ],
            ),
            html.Span(
                className=' '.join(
                    item
                    for item in (
                        'atlanticus-inline-value-row__value',
                        tone_class,
                    )
                    if item
                ),
                children=[state.value],
            ),
        ],
    )
