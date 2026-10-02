# Utilidades de evaluación ADA; aplican truncamiento contractual y generan formato neutro y representación chilena.
from __future__ import annotations

import math
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from numbers import Real

from ada.kpis.core import KpiValueType


def missing_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    try:
        return bool(value != value)
    except Exception:
        return False


def numeric_value(value: object) -> float | int | None:
    if missing_value(value):
        return None
    item = getattr(value, 'item', None)
    if callable(item):
        resolved = item()
        if resolved is not value:
            return numeric_value(resolved)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError('KPI numeric mode received a non-numeric value')
    number = float(value)
    if not math.isfinite(number):
        return None
    if isinstance(value, int):
        return value
    return number


def format_value(
    value: object,
    *,
    value_type: KpiValueType,
    decimals: int,
    is_truncated: bool,
) -> tuple[str, str]:
    if not isinstance(value_type, KpiValueType):
        raise TypeError('value_type must be KpiValueType')
    if value_type is KpiValueType.TEXT:
        resolved = _scalar_item(value)
        if not isinstance(resolved, str):
            raise TypeError('TEXT KPI result requires a string value')
        return resolved, resolved
    if value_type is KpiValueType.BOOLEAN:
        resolved = _scalar_item(value)
        if not isinstance(resolved, bool):
            raise TypeError('BOOLEAN KPI result requires a boolean value')
        text = 'true' if resolved else 'false'
        return text, text
    if value_type is KpiValueType.INTEGER:
        resolved = _scalar_item(value)
        if isinstance(resolved, bool) or not isinstance(resolved, int):
            raise TypeError('INTEGER KPI result requires an integer value')
        neutral = str(resolved)
        return neutral, _chilean_number(neutral)
    number = numeric_value(value)
    if number is None:
        raise ValueError('FLOAT KPI result requires a finite numeric value')
    neutral = _decimal_text(number, decimals=decimals, is_truncated=is_truncated)
    return neutral, _chilean_number(neutral)


def parse_value(value: str, value_type: KpiValueType) -> str | int | float | bool:
    if not isinstance(value, str):
        raise TypeError('KPI scalar value must be str')
    if not isinstance(value_type, KpiValueType):
        raise TypeError('value_type must be KpiValueType')
    if value_type is KpiValueType.TEXT:
        return value
    if value_type is KpiValueType.BOOLEAN:
        if value == 'true':
            return True
        if value == 'false':
            return False
        raise ValueError('BOOLEAN KPI scalar value must be true or false')
    if value_type is KpiValueType.INTEGER:
        try:
            number = int(value)
        except ValueError as error:
            raise ValueError('INTEGER KPI scalar value is invalid') from error
        if str(number) != value:
            raise ValueError('INTEGER KPI scalar value is not canonical')
        return number
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError('FLOAT KPI scalar value is invalid') from error
    if not math.isfinite(number):
        raise ValueError('FLOAT KPI scalar value must be finite')
    return number


def _scalar_item(value: object) -> object:
    item = getattr(value, 'item', None)
    if callable(item):
        resolved = item()
        if resolved is not value:
            return _scalar_item(resolved)
    return value


def _decimal_text(number: float | int, *, decimals: int, is_truncated: bool) -> str:
    try:
        decimal = Decimal(str(number))
    except InvalidOperation as error:
        raise ValueError('KPI numeric value is invalid') from error
    if not decimal.is_finite():
        raise ValueError('KPI numeric value must be finite')
    if is_truncated:
        quantum = Decimal(1).scaleb(-decimals)
        decimal = decimal.quantize(quantum, rounding=ROUND_DOWN)
        if decimal.is_zero():
            decimal = decimal.copy_abs()
        return format(decimal, f'.{decimals}f')
    if decimal.is_zero():
        decimal = decimal.copy_abs()
    return format(decimal, 'f')


def _chilean_number(neutral: str) -> str:
    sign = ''
    body = neutral
    if body.startswith('-'):
        sign = '-'
        body = body[1:]
    integer, separator, fraction = body.partition('.')
    groups: list[str] = []
    while integer:
        groups.append(integer[-3:])
        integer = integer[:-3]
    grouped = '.'.join(reversed(groups)) or '0'
    if not separator:
        return f'{sign}{grouped}'
    return f'{sign}{grouped},{fraction}'
