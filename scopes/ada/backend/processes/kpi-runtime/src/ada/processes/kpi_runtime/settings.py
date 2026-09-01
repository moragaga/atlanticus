from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_runtime.errors import KpiRuntimeConfigurationError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.operational_data.sources import PiSourceProvider

PI_SOURCE_VARIABLE = 'PI_SOURCE'
PI_APPLICATION_VARIABLE = 'PI_APPLICATION'
DISPATCH_APPLICATION_VARIABLE = 'DISPATCH_APPLICATION'
BLOCKGRADE_APPLICATION_VARIABLE = 'BLOCKGRADE_APPLICATION'
REMANENTES_APPLICATION_VARIABLE = 'REMANENTES_APPLICATION'
FABRICA_APPLICATION_VARIABLE = 'FABRICA_APPLICATION'
POLL_INTERVAL_VARIABLE = 'KPI_POLL_INTERVAL_SECONDS'


@dataclass(frozen=True, slots=True)
class KpiRuntimeSettings:
    pi_source: PiSourceProvider
    pi_application: str
    dispatch_application: str | None
    blockgrade_application: str | None
    remanentes_application: str | None
    fabrica_application: str | None
    poll_interval_seconds: float

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> KpiRuntimeSettings:
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
                configuration.get(REMANENTES_APPLICATION_VARIABLE), REMANENTES_APPLICATION_VARIABLE
            ),
            fabrica_application=_optional_application(
                configuration.get(FABRICA_APPLICATION_VARIABLE), FABRICA_APPLICATION_VARIABLE
            ),
            poll_interval_seconds=_positive_float(
                configuration.require(POLL_INTERVAL_VARIABLE), POLL_INTERVAL_VARIABLE
            ),
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key=PI_SOURCE_VARIABLE),
        ConfigurationVariableSpec(key=PI_APPLICATION_VARIABLE),
        ConfigurationVariableSpec(key=DISPATCH_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=BLOCKGRADE_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=REMANENTES_APPLICATION_VARIABLE, required=False),
        ConfigurationVariableSpec(key=FABRICA_APPLICATION_VARIABLE, required=False),
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


def _pi_source(value: str) -> PiSourceProvider:
    if value != value.strip():
        raise KpiRuntimeConfigurationError(
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
        raise KpiRuntimeConfigurationError(
            f'{PI_SOURCE_VARIABLE} must be NOTPII or PI_WEB_API'
        ) from error


def _required_application(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiRuntimeConfigurationError(f'{field} must be non-empty text')
    if value != value.strip():
        raise KpiRuntimeConfigurationError(f'{field} must not contain surrounding whitespace')
    return value


def _optional_application(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    return _required_application(value, field)


def _positive_float(value: str, field: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise KpiRuntimeConfigurationError(f'{field} must contain a positive number') from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise KpiRuntimeConfigurationError(f'{field} must contain a positive number')
    return resolved
