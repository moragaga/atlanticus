# Configuración operativa del proceso Timeseries Delivery.
# Espejo pedagógico; los comentarios no alteran el AST productivo.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
)
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

HISTORIAN_APPLICATION_VARIABLE = 'KPI_HISTORIAN_APPLICATION'
POLL_INTERVAL_VARIABLE = 'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS'
MAX_WORKERS_VARIABLE = 'KPI_TIMESERIES_DELIVERY_MAX_WORKERS'


# El dataclass siguiente representa un contrato de datos explícito.
@dataclass(frozen=True, slots=True)
# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesDeliveryProcessSettings:
    historian_application: str
    poll_interval_seconds: float
    max_workers: int

    @classmethod
# Esta función conserva los contratos e invariantes declarados por el módulo.
    def from_configuration(
        cls,
        configuration: ResolvedConfiguration,
    ) -> KpiTimeseriesDeliveryProcessSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        return cls(
            historian_application=_required_text(
                configuration.require(HISTORIAN_APPLICATION_VARIABLE),
                HISTORIAN_APPLICATION_VARIABLE,
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


# Esta función conserva los contratos e invariantes declarados por el módulo.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key=HISTORIAN_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(key=MAX_WORKERS_VARIABLE, default='2'),
        ConfigurationVariableSpec(
            key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED',
            default='true',
        ),
        ConfigurationVariableSpec(
            key='ATLANTICUS_AZURE_OBSERVABILITY_MODE',
            default='off',
        ),
        ConfigurationVariableSpec(
            key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE',
            required=False,
        ),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING',
            required=False,
            sensitive=True,
        ),
    )


# Esta función conserva los contratos e invariantes declarados por el módulo.
def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must be non-empty text'
        )
    if value != value.strip():
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value


# Esta función conserva los contratos e invariantes declarados por el módulo.
def _non_negative_float(value: str, field_name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a non-negative number'
        ) from error
    if not math.isfinite(resolved) or resolved < 0:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a non-negative number'
        )
    return resolved


# Esta función conserva los contratos e invariantes declarados por el módulo.
def _positive_int(value: str, field_name: str) -> int:
    try:
        resolved = int(value)
    except ValueError as error:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a positive integer'
        ) from error
    if resolved <= 0:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a positive integer'
        )
    return resolved
