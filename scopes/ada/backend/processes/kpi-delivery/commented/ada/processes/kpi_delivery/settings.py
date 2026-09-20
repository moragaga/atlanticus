# Espejo pedagógico del módulo productivo.
# Los comentarios explican la responsabilidad de la frontera sin alterar su semántica.
# La configuración externa conserva conexión, credenciales y base de datos.
# Los demás valores externos son únicamente parámetros operacionales.
# La identidad y topología de contenedores ya no son variables de entorno.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosConfigurationError, CosmosSettings

KPI_RUNTIME_APPLICATION_VARIABLE = 'KPI_RUNTIME_APPLICATION'
POLL_INTERVAL_VARIABLE = 'KPI_DELIVERY_POLL_INTERVAL_SECONDS'


@dataclass(frozen=True, slots=True)
class KpiDeliveryProcessSettings:
    cosmos: CosmosSettings
    kpi_runtime_application: str
    poll_interval_seconds: float

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> KpiDeliveryProcessSettings:
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
            raise KpiDeliveryConfigurationError(str(error)) from error
        return cls(
            cosmos=cosmos,
            kpi_runtime_application=_required_text(
                configuration.require(KPI_RUNTIME_APPLICATION_VARIABLE),
                KPI_RUNTIME_APPLICATION_VARIABLE,
            ),
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE), POLL_INTERVAL_VARIABLE
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_ENDPOINT'),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_KEY', sensitive=True),
        ConfigurationVariableSpec(key='COSMOS_CONSUMPTION_DATABASE_NAME'),
        ConfigurationVariableSpec(key=KPI_RUNTIME_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING',
            required=False,
            sensitive=True,
        ),
    )


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiDeliveryConfigurationError(f'{field_name} must be non-empty text')
    if value != value.strip():
        raise KpiDeliveryConfigurationError(f'{field_name} must not contain surrounding whitespace')
    return value


def _positive_float(value: str, field_name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiDeliveryConfigurationError(
            f'{field_name} must contain a positive number'
        ) from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise KpiDeliveryConfigurationError(f'{field_name} must contain a positive number')
    return resolved
