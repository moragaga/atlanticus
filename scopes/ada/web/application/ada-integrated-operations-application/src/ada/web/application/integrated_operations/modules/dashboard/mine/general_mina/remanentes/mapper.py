from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.readings import (
    KpiPayloadDataState,
    map_kpi_payload_data_state,
)
from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    ValueSeverity,
)

from .definitions import REMANENTES_SUMMARY_KPI_KEY, STOCK_3080_KPI_KEY
from .models import (
    RemanentesState,
    RemanentesSummaryRow,
    RemanentesSummaryState,
    Stock3080State,
)


def map_remanentes_readings(readings: Mapping[str, DisplayValue]) -> RemanentesState:
    summary, summary_status = _map_summary(readings[REMANENTES_SUMMARY_KPI_KEY])
    stock = readings[STOCK_3080_KPI_KEY]
    if stock.status is DisplayStatus.ERROR:
        stock = DisplayValue.invalid()
    return RemanentesState(
        summary=summary,
        summary_status=summary_status,
        stock_3080=Stock3080State(value=stock, status=ValueSeverity.NEUTRAL),
    )


def _map_summary(reading: DisplayValue) -> tuple[RemanentesSummaryState | None, DisplayStatus]:
    if reading.status is not DisplayStatus.OK:
        status = DisplayStatus.INVALID if reading.status is DisplayStatus.ERROR else reading.status
        return None, status
    if not isinstance(reading.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_summary_payload(reading.value), DisplayStatus.OK
    except ValueError:
        return None, DisplayStatus.INVALID


def _map_summary_payload(payload: Mapping[str, object]) -> RemanentesSummaryState:
    if 'data_state' not in payload:
        raise ValueError('Remanentes data_state is required')
    data_state = map_kpi_payload_data_state(payload['data_state'])
    if data_state is KpiPayloadDataState.ERROR:
        return RemanentesSummaryState(rows=(), data_state=data_state)
    rows = payload.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Remanentes rows must be a JSON array')
    return RemanentesSummaryState(
        rows=tuple(_map_summary_row(item) for item in rows),
        data_state=data_state,
    )


def _map_summary_row(value: object) -> RemanentesSummaryRow:
    if not isinstance(value, Mapping):
        raise ValueError('Remanentes row must be an object')
    return RemanentesSummaryRow(
        fase=_require_value(value, 'fase'),
        mineral=_require_value(value, 'mineral'),
        esteril=_require_value(value, 'esteril'),
        baja_ley=_require_value(value, 'baja_ley'),
        total=_require_value(value, 'total'),
    )


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Remanentes field is required: {key}')
    return container[key]
