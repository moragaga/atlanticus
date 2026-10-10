from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import LEYES_DEFINITIONS
from .models import LeyesMetric, LeyesRow, LeyesState


def map_leyes_store(store_data: object) -> LeyesState:
    values, source_status = _latest_values(store_data)
    return LeyesState(
        rows=tuple(
            LeyesRow(
                key=definition.key,
                label=definition.label,
                hora=_metric(values, definition.hora_key, source_status),
                turno=_metric(values, definition.turno_key, source_status),
                dia=_metric(values, definition.dia_key, source_status),
                plan=_metric(values, definition.plan_key, source_status),
            )
            for definition in LEYES_DEFINITIONS
        )
    )


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _metric(
    values: Mapping[str, object] | None,
    kpi_key: str,
    source_status: DisplayStatus,
) -> LeyesMetric:
    if values is None:
        return LeyesMetric(kpi_key, DisplayValue(source_status))
    decoded = decode_kpi_latest_value(values.get(kpi_key), present=kpi_key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        display = DisplayValue.not_mapped()
    elif decoded.state is KpiLatestValueState.MISSING:
        display = DisplayValue.empty()
    elif decoded.state is KpiLatestValueState.ERROR:
        display = DisplayValue.error()
    elif decoded.state is not KpiLatestValueState.OK:
        display = DisplayValue.invalid()
    elif decoded.value_kind != 'value' or isinstance(decoded.parsed_value, bool):
        display = DisplayValue.invalid()
    elif not isinstance(decoded.parsed_value, str | int | float):
        display = DisplayValue.invalid()
    else:
        text = str(decoded.parsed_value)
        display = DisplayValue.ok(text) if text.strip() else DisplayValue.invalid()
    return LeyesMetric(kpi_key, display)
