from __future__ import annotations

import math
from dataclasses import dataclass

# El origen de alarmas es un contrato de dominio, no un ajuste de este job.
from ada_command_center.domain.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration


@dataclass(frozen=True, slots=True)
# Los parámetros de sondeo y concurrencia siguen siendo propios de Delivery.
class AlarmDeliverySettings:
    poll_seconds: float
    max_facts_per_iteration: int
    max_workers: int

    @property
    def source_key(self) -> str:
        return ALARM_CONFIGURATION_SOURCE_KEY

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmDeliverySettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be ResolvedConfiguration')
        try:
            poll_seconds = float(configuration.require('ALARM_DELIVERY_POLL_SECONDS'))
            batch_limit = int(configuration.require('ALARM_DELIVERY_MAX_FACTS_PER_ITERATION'))
            max_workers = int(configuration.require('ALARM_DELIVERY_MAX_WORKERS'))
        except (TypeError, ValueError) as error:
            raise ValueError('Alarm Delivery polling configuration is invalid') from error
        if not math.isfinite(poll_seconds) or poll_seconds <= 0 or batch_limit <= 0:
            raise ValueError('Alarm Delivery polling configuration must be positive')
        if max_workers <= 0:
            raise ValueError('ALARM_DELIVERY_MAX_WORKERS must be positive')
        return cls(
            poll_seconds=poll_seconds,
            max_facts_per_iteration=batch_limit,
            max_workers=max_workers,
        )


# Connection registry y VOLUMEN_PATH siguen siendo administrables en despliegue.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_POLL_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_MAX_FACTS_PER_ITERATION', default='100'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_MAX_WORKERS', default='2'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
