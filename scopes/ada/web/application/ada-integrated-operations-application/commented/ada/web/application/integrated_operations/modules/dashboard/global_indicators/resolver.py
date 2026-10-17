# Este resolvedor obtiene los valores KPI del store y conserva sus estados de presentación.
# Una lectura ausente, inválida o errónea NO degrada Content State.
# El overlay del indicador lo determina Time Status según sus fuentes declaradas.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.kpis.readings import KpiLatestReadings, read_system_latest
from ada.web.ui.display_status import DisplayStatus, DisplayValue
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
    readings = _readings(store_data, binding=binding)
    return tuple(
        ResolvedDashboardGlobalIndicator(
            binding=item,
            state=map_global_indicator(
                definition=item.definition,
                values=_resolve_definition_values(item, readings),
            ),
        )
        for item in binding.indicators
    )


def _readings(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> KpiLatestReadings:
    return read_system_latest(
        store_data,
        tool_key=binding.tool_key,
        destination_key=_GLOBAL_INDICATORS_DESTINATION_KEY,
    )


def _resolve_definition_values(
    binding: DashboardGlobalIndicatorBinding,
    readings: KpiLatestReadings,
) -> dict[str, object]:
    resolved: dict[str, object] = {}
    definition = binding.definition
    for measurement in definition.measurements:
        resolved[measurement.actual_kpi_key] = readings.text(measurement.actual_kpi_key)
        resolved[measurement.plan_kpi_key] = readings.text(measurement.plan_kpi_key)
        if measurement.color_kpi_key is not None:
            resolved[measurement.color_kpi_key] = _color_value(readings, measurement.color_kpi_key)
    if definition.last_measurement is not None:
        resolved[definition.last_measurement.kpi_key] = readings.text(
            definition.last_measurement.kpi_key
        )
    return resolved


def _color_value(readings: KpiLatestReadings, kpi_key: str) -> str | None:
    value: DisplayValue = readings.scalar(kpi_key)
    if (
        value.status is DisplayStatus.OK
        and isinstance(value.value, str)
        and value.value.strip()
    ):
        return value.value
    return None
