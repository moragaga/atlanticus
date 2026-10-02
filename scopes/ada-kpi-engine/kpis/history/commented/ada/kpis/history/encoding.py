from __future__ import annotations

import json
import math
from typing import Any

from ada.kpis.history.errors import KpiHistoryContractError


# Serializa un valor KPI sin perder su tipo JSON y con salida determinística.
def encode_history_value(value: object) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(',', ':'),
        )
    except (TypeError, ValueError) as error:
        raise KpiHistoryContractError('KPI history value must be valid JSON') from error


# Reconstruye el valor nativo y vuelve a validar que no existan números no finitos.
def decode_history_value(value: str | None) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError('KPI history encoded value must be str or None')
    try:
        decoded = json.loads(value, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise KpiHistoryContractError('KPI history encoded value is invalid JSON') from error
    _validate_decoded(decoded)
    return decoded


def _reject_constant(value: str) -> object:
    raise ValueError(value)


def _validate_decoded(value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KpiHistoryContractError('KPI history decoded value contains non-finite numbers')
        return
    if isinstance(value, list):
        for item in value:
            _validate_decoded(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise KpiHistoryContractError('KPI history decoded object keys must be strings')
            _validate_decoded(item)
        return
    raise KpiHistoryContractError('KPI history decoded value is not valid JSON')
