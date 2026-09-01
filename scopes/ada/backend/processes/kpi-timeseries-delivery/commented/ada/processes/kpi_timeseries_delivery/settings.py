# Espejo comentado de la implementación productiva.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
)
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosConfigurationError, CosmosSettings

HISTORIAN_APPLICATION_VARIABLE = 'KPI_HISTORIAN_APPLICATION'
KPI_CONFIGURATION_CONTAINER_VARIABLE = 'KPI_DELIVERY_CONFIGURATION_CONTAINER'
KPI_CONFIGURATION_ITEM_ID_VARIABLE = 'KPI_DELIVERY_CONFIGURATION_ITEM_ID'
KPI_CONFIGURATION_PARTITION_KEY_VARIABLE = 'KPI_DELIVERY_CONFIGURATION_PARTITION_KEY'
KPI_TIMESERIES_CONTAINER_VARIABLE = 'KPI_TIMESERIES_DELIVERY_CONTAINER'
POLL_INTERVAL_VARIABLE = 'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS'


@dataclass(frozen=True, slots=True)
class KpiTimeseriesDeliveryProcessSettings:
    cosmos: CosmosSettings
    historian_application: str
    configuration_container: str
    configuration_item_id: str
    configuration_partition_key: str
    timeseries_container: str
    poll_interval_seconds: float

    @classmethod
    def from_configuration(
        cls,
        configuration: ResolvedConfiguration,
    ) -> KpiTimeseriesDeliveryProcessSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        try:
            cosmos = CosmosSettings(
                endpoint=configuration.require('COSMOS_CONSUMPTION_ENDPOINT'),
                key=configuration.require('COSMOS_CONSUMPTION_KEY'),
                database_name=configuration.require('COSMOS_CONSUMPTION_DATABASE_NAME'),
                allow_insecure_http=configuration.environment.is_local,
            )
        except CosmosConfigurationError as error:
            raise KpiTimeseriesDeliveryConfigurationError(str(error)) from error
        return cls(
            cosmos=cosmos,
            historian_application=_required_text(
                configuration.require(HISTORIAN_APPLICATION_VARIABLE),
                HISTORIAN_APPLICATION_VARIABLE,
            ),
            configuration_container=_required_text(
                configuration.require(KPI_CONFIGURATION_CONTAINER_VARIABLE),
                KPI_CONFIGURATION_CONTAINER_VARIABLE,
            ),
            configuration_item_id=_required_text(
                configuration.require(KPI_CONFIGURATION_ITEM_ID_VARIABLE),
                KPI_CONFIGURATION_ITEM_ID_VARIABLE,
            ),
            configuration_partition_key=_required_text(
                configuration.require(KPI_CONFIGURATION_PARTITION_KEY_VARIABLE),
                KPI_CONFIGURATION_PARTITION_KEY_VARIABLE,
            ),
            timeseries_container=_required_text(
                configuration.require(KPI_TIMESERIES_CONTAINER_VARIABLE),
                KPI_TIMESERIES_CONTAINER_VARIABLE,
            ),
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE),
                POLL_INTERVAL_VARIABLE,
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_ENDPOINT'),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_KEY', sensitive=True),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_DATABASE_NAME'),
        ConfigurationVariableSpec(key=HISTORIAN_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=KPI_CONFIGURATION_CONTAINER_VARIABLE),
        ConfigurationVariableSpec(key=KPI_CONFIGURATION_ITEM_ID_VARIABLE),
        ConfigurationVariableSpec(key=KPI_CONFIGURATION_PARTITION_KEY_VARIABLE),
        ConfigurationVariableSpec(key=KPI_TIMESERIES_CONTAINER_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(
            key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED',
            default='true',
        ),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
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
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must be non-empty text'
        )
    if value != value.strip():
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value


def _positive_float(value: str, field_name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a positive number'
        ) from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise KpiTimeseriesDeliveryConfigurationError(
            f'{field_name} must contain a positive number'
        )
    return resolved
