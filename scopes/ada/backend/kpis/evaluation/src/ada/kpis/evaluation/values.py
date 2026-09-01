from __future__ import annotations

import math
from numbers import Real


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
