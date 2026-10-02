# Espejo pedagógico de KPI Latest Delivery paralelo por Tool: settings.py.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

KPI_RUNTIME_APPLICATION_VARIABLE = 'KPI_RUNTIME_APPLICATION'
POLL_INTERVAL_VARIABLE = 'POLL_INTERVAL_SECONDS'
MAX_WORKERS_VARIABLE = 'KPI_DELIVERY_MAX_WORKERS'


@dataclass(frozen=True, slots=True)
# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryProcessSettings:
    kpi_runtime_application: str
    poll_interval_seconds: float
    max_workers: int

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> KpiDeliveryProcessSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        return cls(
            kpi_runtime_application=_required_text(
                configuration.require(KPI_RUNTIME_APPLICATION_VARIABLE),
                KPI_RUNTIME_APPLICATION_VARIABLE,
            ),
            poll_interval_seconds=_non_negative_float(
                configuration.require(POLL_INTERVAL_VARIABLE),
                POLL_INTERVAL_VARIABLE,
            ),
            max_workers=_positive_int(
                configuration.require(MAX_WORKERS_VARIABLE),
                MAX_WORKERS_VARIABLE,
            ),
        )


# Expone una operación manteniendo validación explícita.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key=KPI_RUNTIME_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(key=MAX_WORKERS_VARIABLE, default='2'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING',
            required=False,
            sensitive=True,
        ),
    )


# Expone una operación manteniendo validación explícita.
def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiDeliveryConfigurationError(f'{field_name} must be non-empty text')
    if value != value.strip():
        raise KpiDeliveryConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value


# Expone una operación manteniendo validación explícita.
def _non_negative_float(value: str, field_name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiDeliveryConfigurationError(
            f'{field_name} must contain a non-negative number'
        ) from error
    if not math.isfinite(resolved) or resolved < 0:
        raise KpiDeliveryConfigurationError(
            f'{field_name} must contain a non-negative number'
        )
    return resolved


# Expone una operación manteniendo validación explícita.
def _positive_int(value: str, field_name: str) -> int:
    try:
        resolved = int(value)
    except ValueError as error:
        raise KpiDeliveryConfigurationError(
            f'{field_name} must contain a positive integer'
        ) from error
    if resolved <= 0:
        raise KpiDeliveryConfigurationError(
            f'{field_name} must contain a positive integer'
        )
    return resolved
