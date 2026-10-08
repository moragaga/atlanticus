# Definiciones inmutables, tonos semanticos y clases opcionales de personalizacion.
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

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
    class_name: str | None = None
    label_class_name: str | None = None
    value_class_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.definition, InlineValueRowDefinition):
            raise TypeError('definition must be InlineValueRowDefinition')
        if not isinstance(self.tone, InlineValueRowTone):
            raise TypeError('tone must be InlineValueRowTone')
        if not isinstance(self.show_border, bool):
            raise TypeError('show_border must be bool')
        _validate_classes(self, ('class_name', 'label_class_name', 'value_class_name'))


@dataclass(frozen=True, slots=True)
class InlineComparisonRowDefinition:
    label: str
    unit: str | None = None
    separator: str = '/'

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError('Inline Comparison Row label cannot be empty')
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit.strip()):
            raise ValueError('Inline Comparison Row unit must be null or a non-empty string')
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


def _validate_classes(state: object, names: tuple[str, ...]) -> None:
    for name in names:
        value = getattr(state, name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f'Inline Value Row {name} must be null or a non-empty string')
