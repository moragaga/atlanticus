# Adapta los dos KPI JSON de MP10 sin recalcular thresholds ni interpretar valores de la API.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus

from .definitions import MP10_HOTEL_MINA_INST_KPI_KEY, MP10_HOTEL_MINA_PROY_KPI_KEY
from .models import MP10MetricState, MP10State

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_mp10_store(store_data: object) -> MP10State:
    values, source_status = _latest_values(store_data)
    # Las dos fuentes conservan su estado collector de manera independiente.
    instant, instant_status = _map_metric(
        values,
        source_status=source_status,
        kpi_key=MP10_HOTEL_MINA_INST_KPI_KEY,
    )
    projection, projection_status = _map_metric(
        values,
        source_status=source_status,
        kpi_key=MP10_HOTEL_MINA_PROY_KPI_KEY,
    )
    return MP10State(
        instant=instant,
        instant_status=instant_status,
        projection=projection,
        projection_status=projection_status,
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


def _map_metric(
    values: Mapping[str, object] | None,
    *,
    source_status: DisplayStatus,
    kpi_key: str,
) -> tuple[MP10MetricState | None, DisplayStatus]:
    if values is None:
        return None, source_status
    decoded = decode_kpi_latest_value(
        values.get(kpi_key),
        present=kpi_key in values,
    )
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID
    try:
        return _map_metric_payload(decoded.value), DisplayStatus.OK
    except (TypeError, ValueError):
        return None, DisplayStatus.INVALID


def _map_metric_payload(payload: Mapping[str, object]) -> MP10MetricState:
    # value, alert y status forman el contrato completo; Web no deriva ninguno de ellos.
    value = _require_value(payload, 'value')
    if not isinstance(value, str | int | float | bool):
        raise TypeError('MP10 value must be a scalar')

    if 'alert' not in payload:
        raise ValueError('MP10 alert is required')
    alert = payload['alert']
    if alert is not None and (
        not isinstance(alert, str) or not alert.strip()
    ):
        raise ValueError('MP10 alert must be null or a non-empty string')

    if 'status' not in payload:
        raise ValueError('MP10 status is required')
    status = map_dashboard_value_status(payload['status'])

    return MP10MetricState(
        value=value,
        alert=alert,
        status=status,
    )


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'MP10 field is required: {key}')
    return container[key]
