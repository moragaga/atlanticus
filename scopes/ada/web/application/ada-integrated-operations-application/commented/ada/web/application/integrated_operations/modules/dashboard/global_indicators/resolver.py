# Espejo comentado: los valores se resuelven para construir la UI, pero el estado operacional se
# calcula para la colección completa. Si falta cualquiera de los KPI configurados, el runtime
# degrada la colección a SOURCE_ERROR; los KPI que no pertenezcan al catálogo no participan.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ada.web.content_state import ContentState
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayValue
from ada.web.ui.global_indicator import GlobalIndicatorState, map_global_indicator

from .bindings import (
    DashboardGlobalIndicatorBinding,
    DashboardGlobalIndicatorsRuntimeBinding,
)

_GLOBAL_INDICATORS_DESTINATION_KEY = 'global_indicators'


@dataclass(frozen=True, slots=True)
class ResolvedDashboardGlobalIndicator:
    binding: DashboardGlobalIndicatorBinding
    state: GlobalIndicatorState


def resolve_dashboard_global_indicators(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> tuple[ResolvedDashboardGlobalIndicator, ...]:
    if not isinstance(binding, DashboardGlobalIndicatorsRuntimeBinding):
        raise TypeError('binding must be DashboardGlobalIndicatorsRuntimeBinding')
    values = _latest_values(store_data, tool_key=binding.tool_key)
    return tuple(
        ResolvedDashboardGlobalIndicator(
            binding=item,
            state=map_global_indicator(
                definition=item.definition,
                values=_resolve_definition_values(item, values),
            ),
        )
        for item in binding.indicators
    )


def resolve_dashboard_global_indicators_runtime_state(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> ContentState:
    if not isinstance(binding, DashboardGlobalIndicatorsRuntimeBinding):
        raise TypeError('binding must be DashboardGlobalIndicatorsRuntimeBinding')
    values = _latest_values(store_data, tool_key=binding.tool_key)
    if values is None:
        return ContentState.SOURCE_ERROR
    # Sólo los KPI declarados por cada definición son obligatorios para esta composición.
    if all(_definition_is_ready(item, values) for item in binding.indicators):
        return ContentState.READY
    return ContentState.SOURCE_ERROR


def _latest_values(store_data: object, *, tool_key: str) -> Mapping[str, object] | None:
    if not isinstance(store_data, Mapping):
        return None
    if store_data.get('tool_key') != tool_key:
        return None
    if store_data.get('destination_key') != _GLOBAL_INDICATORS_DESTINATION_KEY:
        return None
    latest = store_data.get('latest')
    if not isinstance(latest, Mapping):
        return None
    values = latest.get('values')
    return values if isinstance(values, Mapping) else None


def _definition_is_ready(
    binding: DashboardGlobalIndicatorBinding,
    values: Mapping[str, object],
) -> bool:
    definition = binding.definition
    for measurement in definition.measurements:
        if not _display_value_is_ready(values, measurement.actual_kpi_key):
            return False
        if not _display_value_is_ready(values, measurement.plan_kpi_key):
            return False
        if measurement.color_kpi_key is not None and not _color_value_is_ready(
            values,
            measurement.color_kpi_key,
        ):
            return False
    if definition.last_measurement is not None and not _display_value_is_ready(
        values,
        definition.last_measurement.kpi_key,
    ):
        return False
    return True


def _resolve_definition_values(
    binding: DashboardGlobalIndicatorBinding,
    values: Mapping[str, object] | None,
) -> dict[str, object]:
    resolved: dict[str, object] = {}
    definition = binding.definition
    for measurement in definition.measurements:
        resolved[measurement.actual_kpi_key] = _display_value(values, measurement.actual_kpi_key)
        resolved[measurement.plan_kpi_key] = _display_value(values, measurement.plan_kpi_key)
        if measurement.color_kpi_key is not None:
            resolved[measurement.color_kpi_key] = _color_value(values, measurement.color_kpi_key)
    if definition.last_measurement is not None:
        resolved[definition.last_measurement.kpi_key] = _display_value(
            values,
            definition.last_measurement.kpi_key,
        )
    return resolved


def _decoded(values: Mapping[str, object] | None, kpi_key: str):
    present = values is not None and kpi_key in values
    entry = None if values is None else values.get(kpi_key)
    return decode_kpi_latest_value(entry, present=present)


def _display_value_is_ready(values: Mapping[str, object], kpi_key: str) -> bool:
    decoded = _decoded(values, kpi_key)
    return (
        decoded.state is KpiLatestValueState.OK
        and decoded.value_kind == 'value'
        and isinstance(decoded.value, str | int | float | bool)
    )


def _color_value_is_ready(values: Mapping[str, object], kpi_key: str) -> bool:
    decoded = _decoded(values, kpi_key)
    return (
        decoded.state is KpiLatestValueState.OK
        and decoded.value_kind == 'value'
        and isinstance(decoded.value, str)
        and bool(decoded.value.strip())
    )


def _display_value(values: Mapping[str, object] | None, kpi_key: str) -> DisplayValue:
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
    return DisplayValue.invalid()


def _color_value(values: Mapping[str, object] | None, kpi_key: str) -> str | None:
    decoded = _decoded(values, kpi_key)
    if (
        decoded.state is KpiLatestValueState.OK
        and decoded.value_kind == 'value'
        and isinstance(decoded.value, str)
        and decoded.value.strip()
    ):
        return decoded.value
    return None
