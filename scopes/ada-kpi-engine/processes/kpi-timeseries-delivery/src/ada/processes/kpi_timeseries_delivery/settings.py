from __future__ import annotations

from dataclasses import dataclass

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
)
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

HISTORIAN_APPLICATION_VARIABLE = 'KPI_HISTORIAN_APPLICATION'
KPI_MATERIALIZATION_APPLICATION_VARIABLE = 'KPI_MATERIALIZATION_APPLICATION'
MAX_WORKERS_VARIABLE = 'KPI_TIMESERIES_DELIVERY_MAX_WORKERS'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesDeliveryProcessSettings:
    historian_application: str
    kpi_materialization_application: str
    max_workers: int

    @classmethod
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
            kpi_materialization_application=_required_text(
                configuration.require(KPI_MATERIALIZATION_APPLICATION_VARIABLE),
                KPI_MATERIALIZATION_APPLICATION_VARIABLE,
            ),
            max_workers=_positive_int(
                configuration.require(MAX_WORKERS_VARIABLE),
                MAX_WORKERS_VARIABLE,
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=HISTORIAN_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=KPI_MATERIALIZATION_APPLICATION_VARIABLE),
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


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiTimeseriesDeliveryConfigurationError(f'{field_name} must be non-empty text')
    if value != value.strip():
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value


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
