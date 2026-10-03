from __future__ import annotations

from collections.abc import Iterable, Mapping

from .definitions import (
    GlobalIndicatorDefinition,
    GlobalIndicatorLastMeasurementDefinition,
    GlobalIndicatorMeasurementDefinition,
)
from .models import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
)


def map_global_indicator(
    *,
    definition: GlobalIndicatorDefinition,
    values: Mapping[str, object],
) -> GlobalIndicatorState:
    if not isinstance(definition, GlobalIndicatorDefinition):
        raise TypeError('definition must be a GlobalIndicatorDefinition')
    if not isinstance(values, Mapping):
        raise TypeError('values must be a mapping')
    return GlobalIndicatorState(
        key=definition.key,
        label=definition.label,
        unit=definition.unit,
        measurements=tuple(
            _map_measurement(definition=item, values=values) for item in definition.measurements
        ),
        last_measurement=(
            None
            if definition.last_measurement is None
            else _map_last_measurement(
                definition=definition.last_measurement,
                values=values,
            )
        ),
    )


def map_global_indicators(
    *,
    definitions: Iterable[GlobalIndicatorDefinition],
    values: Mapping[str, object],
) -> GlobalIndicatorCollection:
    if not isinstance(values, Mapping):
        raise TypeError('values must be a mapping')
    resolved = tuple(definitions)
    if not all(isinstance(item, GlobalIndicatorDefinition) for item in resolved):
        raise TypeError('definitions must contain GlobalIndicatorDefinition values')
    return GlobalIndicatorCollection(
        tuple(map_global_indicator(definition=definition, values=values) for definition in resolved)
    )


def _map_measurement(
    *,
    definition: GlobalIndicatorMeasurementDefinition,
    values: Mapping[str, object],
) -> GlobalIndicatorMeasurementState:
    return GlobalIndicatorMeasurementState(
        key=definition.key,
        label=definition.label,
        actual_value=values[definition.actual_kpi_key],
        plan_value=values[definition.plan_kpi_key],
        actual_kpi_key=definition.actual_kpi_key,
        plan_kpi_key=definition.plan_kpi_key,
    )


def _map_last_measurement(
    *,
    definition: GlobalIndicatorLastMeasurementDefinition,
    values: Mapping[str, object],
) -> GlobalIndicatorLastMeasurementState:
    return GlobalIndicatorLastMeasurementState(
        key=definition.key,
        label=definition.label,
        actual_value=values[definition.kpi_key],
        actual_kpi_key=definition.kpi_key,
    )
