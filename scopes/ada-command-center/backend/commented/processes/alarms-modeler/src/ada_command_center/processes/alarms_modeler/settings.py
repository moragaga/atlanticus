# Espejo pedagógico en español del archivo productivo equivalente.
# Mantiene exactamente el mismo comportamiento; los comentarios explican la intención.
# Este incremento prioriza el flujo vertical Runtime -> Modeler -> Delivery -> Cosmos.

from __future__ import annotations

import math
from dataclasses import dataclass

from ada_command_center.domain.alarms.identity import ALARM_CONFIGURATION_SOURCE_KEY
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration


@dataclass(frozen=True, slots=True)
class AlarmModelerSettings:
    poll_seconds: float

    @property
    def source_key(self) -> str:
        return ALARM_CONFIGURATION_SOURCE_KEY

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmModelerSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be ResolvedConfiguration')
        try:
            poll_seconds = float(configuration.require('ALARM_MODELER_POLL_SECONDS'))
        except (TypeError, ValueError) as error:
            raise ValueError('Alarm Modeler polling configuration is invalid') from error
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError('Alarm Modeler polling configuration must be positive')
        return cls(poll_seconds=poll_seconds)


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_MODELER_POLL_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
