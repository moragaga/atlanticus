from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from ada.web.ui.display_status import DisplayValue


class StockpileVariant(StrEnum):
    VARIABLE_HEIGHT = 'variable_height'
    FIXED_PROFILE = 'fixed_profile'


def _validate_color(value: str | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != '#'
        or any(character not in '0123456789abcdefABCDEF' for character in value[1:])
    ):
        raise ValueError(f'{name} must be a six-digit hexadecimal color or null')


def _validate_positive_size(value: int | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
        raise ValueError(f'{name} must be a positive integer or null')


def _validate_finite_number(value: float | None, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f'{name} must be a finite number')


@dataclass(frozen=True, slots=True)
class StockpileDefinition:
    key: str
    variant: StockpileVariant
    scale_max_m: float | None = None
    max_height_m: float | None = None
    max_width_px: int | None = None
    max_height_px: int | None = None
    percentage_background_color: str | None = None
    percentage_text_color: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError('Stockpile key must be a non-empty string')
        if not isinstance(self.variant, StockpileVariant):
            raise TypeError('Stockpile variant must be StockpileVariant')
        for name in ('max_width_px', 'max_height_px'):
            _validate_positive_size(getattr(self, name), name)
        for name in ('percentage_background_color', 'percentage_text_color'):
            _validate_color(getattr(self, name), name)
        if self.variant is StockpileVariant.VARIABLE_HEIGHT:
            _validate_finite_number(self.scale_max_m, 'scale_max_m')
            if self.scale_max_m <= 0:
                raise ValueError('scale_max_m must be greater than zero')
            if self.max_height_m is not None:
                _validate_finite_number(self.max_height_m, 'max_height_m')
                if not 0 < self.max_height_m <= self.scale_max_m:
                    raise ValueError('max_height_m must be positive and within the scale')
        elif self.scale_max_m is not None or self.max_height_m is not None:
            raise ValueError('Fixed-profile stockpiles cannot specify height limits')


@dataclass(frozen=True, slots=True)
class StockpileValues:
    percent: DisplayValue
    height_m: DisplayValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.percent, DisplayValue):
            raise TypeError('Stockpile percent must be DisplayValue')
        if self.height_m is not None and not isinstance(self.height_m, DisplayValue):
            raise TypeError('Stockpile height_m must be DisplayValue or null')


def validate_stockpile_values(definition: StockpileDefinition, values: StockpileValues) -> None:
    if not isinstance(definition, StockpileDefinition):
        raise TypeError('definition must be StockpileDefinition')
    if not isinstance(values, StockpileValues):
        raise TypeError('values must be StockpileValues')
    if definition.variant is StockpileVariant.VARIABLE_HEIGHT and values.height_m is None:
        raise ValueError('Variable-height stockpiles require height_m')
    if definition.variant is StockpileVariant.FIXED_PROFILE and values.height_m is not None:
        raise ValueError('Fixed-profile stockpiles cannot specify height_m')
