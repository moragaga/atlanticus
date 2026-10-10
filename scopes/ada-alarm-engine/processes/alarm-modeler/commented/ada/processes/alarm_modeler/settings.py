# Declara variables de configuración y comprueba que sus límites son operables.
from __future__ import annotations

import math
from dataclasses import dataclass

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration


@dataclass(frozen=True, slots=True)
# Responsabilidad de AlarmModelerSettings: ejecutar el contrato local sin efectos implícitos.
class AlarmModelerSettings:
    runtime_application: str
    poll_seconds: float
    rotation_seconds: float
    max_visible_slots: int

    @classmethod
    # Convierte valores efectivos y valida identidades y cadencias de configuración.
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmModelerSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be ResolvedConfiguration')
        application = configuration.require('ALARM_RUNTIME_APPLICATION')
        own_application = configuration.require('APPLICATION')
        if (
            not application
            or application != application.strip()
            or application in ('.', '..')
            or '/' in application
            or '\\' in application
        ):
            raise ValueError('ALARM_RUNTIME_APPLICATION must be a normalized application name')
        if application == own_application:
            raise ValueError('Modeler and Runtime must use different APPLICATION names')
        poll = _positive_float(configuration.require('ALARM_MODELER_POLL_SECONDS'), 'ALARM_MODELER_POLL_SECONDS')
        rotation = _positive_float(
            configuration.require('ALARM_MODELER_ROTATION_SECONDS'), 'ALARM_MODELER_ROTATION_SECONDS'
        )
        slots = _positive_int(
            configuration.require('ALARM_MODELER_MAX_VISIBLE_SLOTS'),
            'ALARM_MODELER_MAX_VISIBLE_SLOTS',
        )
        return cls(
            runtime_application=application,
            poll_seconds=poll,
            rotation_seconds=rotation,
            max_visible_slots=slots,
        )


# Responsabilidad de _positive_float: ejecutar el contrato local sin efectos implícitos.
def _positive_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{label} must be a positive finite number') from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f'{label} must be a positive finite number')
    return number


# Responsabilidad de _positive_int: ejecutar el contrato local sin efectos implícitos.
def _positive_int(value: str, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{label} must be a positive integer') from error
    if number <= 0:
        raise ValueError(f'{label} must be a positive integer')
    return number


# Enumera cada variable necesaria, incluyendo su valor por defecto.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_RUNTIME_APPLICATION'),
        ConfigurationVariableSpec(key='ALARM_MODELER_POLL_SECONDS', default='1'),
        ConfigurationVariableSpec(key='ALARM_MODELER_ROTATION_SECONDS', default='30'),
        ConfigurationVariableSpec(key='ALARM_MODELER_MAX_VISIBLE_SLOTS', default='6'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
