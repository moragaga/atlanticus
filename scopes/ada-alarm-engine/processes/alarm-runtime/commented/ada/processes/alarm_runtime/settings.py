# Configuración mínima del proceso Alarm Runtime y su frecuencia de consulta.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.alarm_runtime.errors import AlarmRuntimeConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

POLL_INTERVAL_VARIABLE = 'ALARM_RUNTIME_POLL_SECONDS'


@dataclass(frozen=True, slots=True)
class AlarmRuntimeSettings:
    poll_interval_seconds: float

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmRuntimeSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        return cls(
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE), POLL_INTERVAL_VARIABLE
            )
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='5'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )


def _positive_float(value: str, name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise AlarmRuntimeConfigurationError(f'{name} must contain a positive number') from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise AlarmRuntimeConfigurationError(f'{name} must contain a positive number')
    return resolved
