from __future__ import annotations

import math
from dataclasses import dataclass

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.runtime.storage import validate_path_segment


@dataclass(frozen=True, slots=True)
class AlarmDeliverySettings:
    modeler_application: str
    poll_seconds: float
    max_workers: int
    cosmos_provision_mode: str

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmDeliverySettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('Delivery configuration must be ResolvedConfiguration')
        modeler = validate_path_segment(
            configuration.require('ALARM_MODELER_APPLICATION'), name='modeler_application'
        )
        application = validate_path_segment(
            configuration.require('APPLICATION'), name='application'
        )
        if modeler == application:
            raise ValueError('Delivery and Modeler must use different APPLICATION names')
        try:
            poll = float(configuration.require('ALARM_DELIVERY_POLL_SECONDS'))
            workers_text = configuration.require('ALARM_DELIVERY_MAX_WORKERS')
            if not workers_text.isdecimal() or workers_text.startswith('0'):
                raise ValueError('Invalid worker count')
            workers = int(workers_text)
        except (TypeError, ValueError) as error:
            raise ValueError('Alarm Delivery settings are invalid') from error
        if not math.isfinite(poll) or poll <= 0 or not 1 <= workers <= 64:
            raise ValueError('Alarm Delivery poll or max_workers is out of range')
        mode = configuration.require('ADA_COSMOS_PROVISION_MODE')
        if mode not in ('OFF', 'ENSURE'):
            raise ValueError('ADA_COSMOS_PROVISION_MODE must be OFF or ENSURE')
        return cls(
            modeler_application=modeler,
            poll_seconds=poll,
            max_workers=workers,
            cosmos_provision_mode=mode,
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_MODELER_APPLICATION'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_POLL_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ALARM_DELIVERY_MAX_WORKERS', default='4'),
        ConfigurationVariableSpec(key='ADA_COSMOS_PROVISION_MODE', default='OFF'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
