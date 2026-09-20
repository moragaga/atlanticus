# Espejo pedagógico del módulo productivo.
# Los comentarios explican intención sin alterar comportamiento ni contratos.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_historian.errors import KpiHistorianConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

KPI_RUNTIME_APPLICATION_VARIABLE = 'KPI_RUNTIME_APPLICATION'
POLL_INTERVAL_VARIABLE = 'KPI_HISTORIAN_POLL_INTERVAL_SECONDS'
# El flag es explícito y seguro por defecto: producción conserva el skip CURRENT.
REPROCESS_CURRENT_VARIABLE = 'REPROCESS_CURRENT'


@dataclass(frozen=True, slots=True)
class KpiHistorianSettings:
    kpi_runtime_application: str
    poll_interval_seconds: float
    reprocess_current: bool

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> KpiHistorianSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        return cls(
            kpi_runtime_application=_required_text(
                configuration.require(KPI_RUNTIME_APPLICATION_VARIABLE),
                KPI_RUNTIME_APPLICATION_VARIABLE,
            ),
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE),
                POLL_INTERVAL_VARIABLE,
            ),
            reprocess_current=_boolean(
                configuration.require(REPROCESS_CURRENT_VARIABLE),
                REPROCESS_CURRENT_VARIABLE,
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key=KPI_RUNTIME_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(key=REPROCESS_CURRENT_VARIABLE, default='false'),
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
        raise KpiHistorianConfigurationError(f'{field_name} must be non-empty text')
    if value != value.strip():
        raise KpiHistorianConfigurationError(
            f'{field_name} must not contain surrounding whitespace'
        )
    return value


def _positive_float(value: str, field_name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiHistorianConfigurationError(
            f'{field_name} must contain a positive number'
        ) from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise KpiHistorianConfigurationError(f'{field_name} must contain a positive number')
    return resolved


# Se aceptan sólo literales true/false para evitar coerciones ambiguas de configuración.
def _boolean(value: str, field_name: str) -> bool:
    if not isinstance(value, str) or value != value.strip():
        raise KpiHistorianConfigurationError(f'{field_name} must be true or false')
    normalized = value.lower()
    if normalized == 'true':
        return True
    if normalized == 'false':
        return False
    raise KpiHistorianConfigurationError(f'{field_name} must be true or false')
