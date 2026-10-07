from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import REMANENTES_SUMMARY_KPI_KEY, STOCK_3080_KPI_KEY
from .models import (
    RemanentesState,
    RemanentesSummaryRow,
    RemanentesSummaryState,
    Stock3080State,
)

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.ERROR,
}


def map_remanentes_store(store_data: object) -> RemanentesState:
    values, source_status = _latest_values(store_data)
    summary, summary_status = _map_summary(values, source_status=source_status)
    return RemanentesState(
        summary=summary,
        summary_status=summary_status,
        stock_3080=Stock3080State(
            value=_display_value(
                values,
                STOCK_3080_KPI_KEY,
                source_status=source_status,
            ),
            status=DashboardValueStatus.NEUTRAL,
        ),
    )


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.EMPTY
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _map_summary(
    values: Mapping[str, object] | None,
    *,
    source_status: DisplayStatus,
) -> tuple[RemanentesSummaryState | None, DisplayStatus]:
    if values is None:
        return None, source_status
    decoded = _decoded(values, REMANENTES_SUMMARY_KPI_KEY)
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_summary_payload(decoded.value), DisplayStatus.OK
    except ValueError:
        return None, DisplayStatus.INVALID


def _map_summary_payload(payload: Mapping[str, object]) -> RemanentesSummaryState:
    if 'data_state' not in payload:
        raise ValueError('Remanentes data_state is required')
    data_state = map_dashboard_data_state(payload['data_state'])
    if data_state is DashboardDataState.ERROR:
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


def _display_value(
    values: Mapping[str, object] | None,
    kpi_key: str,
    *,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        if source_status is DisplayStatus.EMPTY:
            return DisplayValue.empty()
        if source_status is DisplayStatus.INVALID:
            return DisplayValue.invalid()
        if source_status is DisplayStatus.ERROR:
            return DisplayValue.error()
        return DisplayValue.not_mapped()
    decoded = _decoded(values, kpi_key)
    if decoded.state is KpiLatestValueState.OK:
        if decoded.value_kind != 'value' or not isinstance(
            decoded.value,
            str | int | float | bool,
        ):
            return DisplayValue.invalid()
        return DisplayValue.ok(decoded.value)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.INVALID:
        return DisplayValue.invalid()
    return DisplayValue.error()


def _decoded(values: Mapping[str, object], kpi_key: str):
    return decode_kpi_latest_value(
        values.get(kpi_key),
        present=kpi_key in values,
    )


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Remanentes field is required: {key}')
    return container[key]
