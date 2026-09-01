# Espejo pedagógico: mantiene los contratos KPI y añade comentarios en español sin cambiar el AST productivo.
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TypeAlias

KpiScalar: TypeAlias = str | int | float | bool
KpiJsonValue: TypeAlias = KpiScalar | None | list['KpiJsonValue'] | dict[str, 'KpiJsonValue']
KpiNativeValue: TypeAlias = KpiJsonValue


def normalize_kpi_value(value: object) -> KpiNativeValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('KPI value must not contain non-finite numbers')
        return value
    item = getattr(value, 'item', None)
    if callable(item):
        resolved = item()
        if resolved is not value:
            return normalize_kpi_value(resolved)
    if isinstance(value, Mapping):
        normalized: dict[str, KpiJsonValue] = {}
        for key, item_value in value.items():
            if not isinstance(key, str):
                raise TypeError('KPI JSON object keys must be strings')
            normalized[key] = normalize_kpi_value(item_value)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [normalize_kpi_value(item_value) for item_value in value]
    raise TypeError(f'unsupported KPI value type: {type(value).__name__}')
