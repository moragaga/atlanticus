# Espejo pedagógico en español. Misma ejecución y contratos del archivo productivo.
from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.alarm_runtime.errors import AlarmRuntimeConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.operational_data.sources import PiSourceProvider

PI_SOURCE_VARIABLE = 'PI_SOURCE'
PI_APPLICATION_VARIABLE = 'PI_APPLICATION'
DISPATCH_APPLICATION_VARIABLE = 'DISPATCH_APPLICATION'
BLOCKGRADE_APPLICATION_VARIABLE = 'BLOCKGRADE_APPLICATION'
REMANENTES_APPLICATION_VARIABLE = 'REMANENTES_APPLICATION'
FABRICA_PLANES_APPLICATION_VARIABLE = 'FABRICA_PLANES_APPLICATION'
FABRICA_KPIS_APPLICATION_VARIABLE = 'FABRICA_KPIS_APPLICATION'
METEODATA_APPLICATION_VARIABLE = 'METEODATA_APPLICATION'
POLL_INTERVAL_VARIABLE = 'ALARM_RUNTIME_POLL_SECONDS'
WAL_SEGMENT_BYTES_VARIABLE = 'ALARM_RUNTIME_WAL_SEGMENT_BYTES'
CHECKPOINT_SECONDS_VARIABLE = 'ALARM_RUNTIME_CHECKPOINT_SECONDS'
FACTS_PUBLISH_SECONDS_VARIABLE = 'ALARM_RUNTIME_FACTS_PUBLISH_SECONDS'


@dataclass(frozen=True, slots=True)
# Configuración validada del proceso, con polling operacional independiente de otras cadencias.
class AlarmRuntimeSettings:
    pi_source: PiSourceProvider
    pi_application: str
    dispatch_application: str | None
    blockgrade_application: str | None
    remanentes_application: str | None
    fabrica_planes_application: str | None
    fabrica_kpis_application: str | None
    meteodata_application: str | None
    poll_interval_seconds: float
    max_wal_segment_bytes: int = 262144
    checkpoint_interval_seconds: float = 60.0
    facts_publish_interval_seconds: float = 10.0

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> AlarmRuntimeSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        return cls(
            pi_source=_pi_source(configuration.require(PI_SOURCE_VARIABLE)),
            pi_application=_required_application(
                configuration.require(PI_APPLICATION_VARIABLE), PI_APPLICATION_VARIABLE
            ),
            dispatch_application=_optional_application(
                configuration.get(DISPATCH_APPLICATION_VARIABLE), DISPATCH_APPLICATION_VARIABLE
            ),
            blockgrade_application=_optional_application(
                configuration.get(BLOCKGRADE_APPLICATION_VARIABLE), BLOCKGRADE_APPLICATION_VARIABLE
            ),
            remanentes_application=_optional_application(
                configuration.get(REMANENTES_APPLICATION_VARIABLE),
                REMANENTES_APPLICATION_VARIABLE,
            ),
            fabrica_planes_application=_optional_application(
                configuration.get(FABRICA_PLANES_APPLICATION_VARIABLE),
                FABRICA_PLANES_APPLICATION_VARIABLE,
            ),
            fabrica_kpis_application=_optional_application(
                configuration.get(FABRICA_KPIS_APPLICATION_VARIABLE),
                FABRICA_KPIS_APPLICATION_VARIABLE,
            ),
            meteodata_application=_optional_application(
                configuration.get(METEODATA_APPLICATION_VARIABLE), METEODATA_APPLICATION_VARIABLE
            ),
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE), POLL_INTERVAL_VARIABLE
            ),
            max_wal_segment_bytes=_positive_int(
                configuration.get(WAL_SEGMENT_BYTES_VARIABLE) or '262144',
                WAL_SEGMENT_BYTES_VARIABLE,
            ),
            checkpoint_interval_seconds=_positive_float(
                configuration.get(CHECKPOINT_SECONDS_VARIABLE) or '60',
                CHECKPOINT_SECONDS_VARIABLE,
            ),
            facts_publish_interval_seconds=_positive_float(
                configuration.get(FACTS_PUBLISH_SECONDS_VARIABLE) or '10',
                FACTS_PUBLISH_SECONDS_VARIABLE,
            ),
        )


# Declara las variables de configuración y el polling por defecto de un segundo.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=PI_SOURCE_VARIABLE),
        ConfigurationVariableSpec(key=PI_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=DISPATCH_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=BLOCKGRADE_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=REMANENTES_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=FABRICA_PLANES_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=FABRICA_KPIS_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=METEODATA_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='1'),
        ConfigurationVariableSpec(key=WAL_SEGMENT_BYTES_VARIABLE, default='262144'),
        ConfigurationVariableSpec(key=CHECKPOINT_SECONDS_VARIABLE, default='60'),
        ConfigurationVariableSpec(key=FACTS_PUBLISH_SECONDS_VARIABLE, default='10'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )


def _pi_source(value: str) -> PiSourceProvider:
    if value != value.strip():
        raise AlarmRuntimeConfigurationError(
            f'{PI_SOURCE_VARIABLE} must not contain surrounding whitespace'
        )
    normalized = value.lower()
    aliases = {
        'notpii': PiSourceProvider.NOTPII,
        'pi_web_api': PiSourceProvider.PI_WEB_API,
        'pi-web-api': PiSourceProvider.PI_WEB_API,
    }
    try:
        return aliases[normalized]
    except KeyError as error:
        raise AlarmRuntimeConfigurationError(
            f'{PI_SOURCE_VARIABLE} must be NOTPII or PI_WEB_API'
        ) from error


def _required_application(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AlarmRuntimeConfigurationError(f'{field} must be non-empty text')
    if value != value.strip():
        raise AlarmRuntimeConfigurationError(f'{field} must not contain surrounding whitespace')
    return value


def _optional_application(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    return _required_application(value, field)


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AlarmRuntimeConfigurationError(f'{name} must be an integer >= 512') from error
    if isinstance(value, bool) or parsed < 512:
        raise AlarmRuntimeConfigurationError(f'{name} must be an integer >= 512')
    return parsed


def _positive_float(value: str, name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise AlarmRuntimeConfigurationError(f'{name} must contain a positive number') from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise AlarmRuntimeConfigurationError(f'{name} must contain a positive number')
    return resolved
