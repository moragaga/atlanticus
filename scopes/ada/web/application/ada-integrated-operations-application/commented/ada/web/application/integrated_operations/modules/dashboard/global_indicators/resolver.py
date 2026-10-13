# Los indicadores globales se alimentan del mismo KPI Collector que Mina y Planta.
# Su store es de sistema, por lo que se lee con read_system_latest y se valida
# explícitamente la identidad de la Tool y el destino global_indicators.
from __future__ import annotations

from dataclasses import dataclass

from ada.web.content_state import ContentState
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


def resolve_dashboard_global_indicators_runtime_state(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> ContentState:
    if not isinstance(binding, DashboardGlobalIndicatorsRuntimeBinding):
        raise TypeError('binding must be DashboardGlobalIndicatorsRuntimeBinding')
    readings = _readings(store_data, binding=binding)
    # Se conserva el criterio vigente: toda la colección debe estar lista.
    # No se altera la política de overlays de Content State en este incremento.
    if readings.source_status is not DisplayStatus.OK:
        return ContentState.SOURCE_ERROR
    if all(_definition_is_ready(item, readings) for item in binding.indicators):
        return ContentState.READY
    return ContentState.SOURCE_ERROR


def _readings(
    store_data: object,
    *,
    binding: DashboardGlobalIndicatorsRuntimeBinding,
) -> KpiLatestReadings:
    # Valida tool_key/destination_key y obtiene el mismo contrato de lecturas
    # utilizado por los decoders de componentes, sin deserialización paralela.
    return read_system_latest(
        store_data,
        tool_key=binding.tool_key,
        destination_key=_GLOBAL_INDICATORS_DESTINATION_KEY,
    )


def _definition_is_ready(
    binding: DashboardGlobalIndicatorBinding,
    readings: KpiLatestReadings,
) -> bool:
    definition = binding.definition
    for measurement in definition.measurements:
        if readings.text(measurement.actual_kpi_key).status is not DisplayStatus.OK:
            return False
        if readings.text(measurement.plan_kpi_key).status is not DisplayStatus.OK:
            return False
        if measurement.color_kpi_key is not None and _color_value(
            readings,
            measurement.color_kpi_key,
        ) is None:
            return False
    if definition.last_measurement is not None and readings.text(
        definition.last_measurement.kpi_key,
    ).status is not DisplayStatus.OK:
        return False
    return True


def _resolve_definition_values(
    binding: DashboardGlobalIndicatorBinding,
    readings: KpiLatestReadings,
) -> dict[str, object]:
    resolved: dict[str, object] = {}
    definition = binding.definition
    for measurement in definition.measurements:
        # text() toma parsed_value para la presentación (formato amigable).
        resolved[measurement.actual_kpi_key] = readings.text(measurement.actual_kpi_key)
        resolved[measurement.plan_kpi_key] = readings.text(measurement.plan_kpi_key)
        if measurement.color_kpi_key is not None:
            resolved[measurement.color_kpi_key] = _color_value(readings, measurement.color_kpi_key)
    if definition.last_measurement is not None:
        resolved[definition.last_measurement.kpi_key] = readings.text(
            definition.last_measurement.kpi_key,
        )
    return resolved


def _color_value(readings: KpiLatestReadings, kpi_key: str) -> str | None:
    # La clase de color se obtiene del valor raw para no aplicar formatos de
    # presentación a una clase CSS. El renderer ya valida tokens CSS seguros.
    value: DisplayValue = readings.scalar(kpi_key)
    if (
        value.status is DisplayStatus.OK
        and isinstance(value.value, str)
        and value.value.strip()
    ):
        return value.value
    return None
