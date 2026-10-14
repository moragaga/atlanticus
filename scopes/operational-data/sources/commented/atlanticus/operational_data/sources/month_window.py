# Espejo pedagógico de la resolución temporal para inputs de Fábrica.
# Las vistas DAILY/WEEKLY guardan archivos por mes, pero siguen siendo vistas lógicas distintas.
from __future__ import annotations

from datetime import UTC, datetime

from atlanticus.operational_data.core import (
    DataSource,
    TimeWindow,
    TimeWindowUnit,
    normalize_utc_second,
)

# Solo Fábrica interpreta una ventana MONTHS como meses calendario incluyendo el actual.
_FABRICA_SOURCES = frozenset({DataSource.FABRICA_PLANES, DataSource.FABRICA_KPIS})


def time_window_start(*, source: DataSource, window: TimeWindow, as_of: datetime) -> datetime:
    # Las demás fuentes conservan las ventanas móviles originales de TimeWindow.
    if source not in _FABRICA_SOURCES or window.unit is not TimeWindowUnit.MONTHS:
        return window.start_from(as_of)
    # El ciclo y las particiones físicas de Fábrica utilizan el calendario UTC.
    timestamp = normalize_utc_second(as_of, field_name='as_of')
    # value=1 inicia el primer día del mes actual; value=2 incluye el mes anterior.
    month_index = timestamp.year * 12 + timestamp.month - window.value
    year, zero_based_month = divmod(month_index, 12)
    return datetime(year, zero_based_month + 1, 1, tzinfo=UTC)
