from __future__ import annotations

# Se separa validez de la lectura KPI de su posible interpretación numérica.

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite

from ada.web.ui.display_status import DisplayStatus, DisplayValue

_NUMBER = re.compile(r'^\+?(?:\d+(?:[.,]\d+)?|[.,]\d+)$')


@dataclass(frozen=True, slots=True)
# La lectura conserva el texto original si está validado y su número solo para geometría.
class StockpileReading:
    status: DisplayStatus
    text: str | None = None
    number: float | None = None


# Si el origen degrada el valor se respeta ese estado; con OK se valida el texto numérico.
# Se acepta coma o punto decimal, pero no porcentajes con símbolo ni separadores ambiguos.
def resolve_stockpile_reading(value: DisplayValue, *, percentage: bool) -> StockpileReading:
    if not isinstance(value, DisplayValue):
        raise TypeError('Stockpile reading must be DisplayValue')
    if value.status is not DisplayStatus.OK:
        return StockpileReading(status=value.status)

    raw = value.value
    if isinstance(raw, bool) or not isinstance(raw, str | int | float | Decimal):
        return StockpileReading(status=DisplayStatus.INVALID)
    if isinstance(raw, float) and not isfinite(raw):
        return StockpileReading(status=DisplayStatus.INVALID)

    original_text = str(raw).strip()
    if not _NUMBER.fullmatch(original_text):
        return StockpileReading(status=DisplayStatus.INVALID)
    try:
        parsed = Decimal(original_text.replace(',', '.'))
    except InvalidOperation:
        return StockpileReading(status=DisplayStatus.INVALID)
    if not parsed.is_finite() or parsed < 0 or (percentage and parsed > 100):
        return StockpileReading(status=DisplayStatus.INVALID)
    try:
        numeric = float(parsed)
    except OverflowError:
        return StockpileReading(status=DisplayStatus.INVALID)
    if not isfinite(numeric):
        return StockpileReading(status=DisplayStatus.INVALID)
    return StockpileReading(status=DisplayStatus.OK, text=original_text, number=numeric)
