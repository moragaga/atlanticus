from __future__ import annotations

import math
from dataclasses import dataclass

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration


@dataclass(frozen=True, slots=True)
class AlarmDeliverySettings:
    source_key: str
    poll_seconds: float
    max_facts_per_iteration: int

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmDeliverySettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be ResolvedConfiguration')
        source_key = configuration.require('ALARM_CONFIGURATION_SOURCE_KEY')
        if not source_key or source_key != source_key.strip():
            raise ValueError('ALARM_CONFIGURATION_SOURCE_KEY must be non-empty text')
        try:
            poll_seconds = float(configuration.require('ALARM_DELIVERY_POLL_SECONDS'))
            batch_limit = int(configuration.require('ALARM_DELIVERY_MAX_FACTS_PER_ITERATION'))
        except (TypeError, ValueError) as error:
            raise ValueError('Alarm Delivery polling configuration is invalid') from error
        if not math.isfinite(poll_seconds) or poll_seconds <= 0 or batch_limit <= 0:
            raise ValueError('Alarm Delivery polling configuration must be positive')
        return cls(
            source_key=source_key,
            poll_seconds=poll_seconds,
            max_facts_per_iteration=batch_limit,
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_CONFIGURATION_SOURCE_KEY'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_POLL_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_MAX_FACTS_PER_ITERATION', default='100'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
