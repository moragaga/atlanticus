from __future__ import annotations

# La conversión de ts_last no tiene default: se debe validar con Meteodata antes de publicar proyección.

from dataclasses import dataclass

from atlanticus.configuration import (
    ConfigurationValueError,
    ConfigurationVariableSpec,
    ResolvedConfiguration,
)
from atlanticus.connectivity.http import HttpAuthMode, HttpConfigurationError, HttpSettings
from atlanticus.operational_data.processes.meteodata.errors import (
    MeteodataProcessConfigurationError,
)


@dataclass(frozen=True, slots=True)
class MeteodataSettings:
    http: HttpSettings
    lookback_minutes: int
    retry_delay_seconds: int

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> MeteodataSettings:
        try:
            return cls(
                http=HttpSettings(
                    base_url=configuration.require('METEODATA_BASE_URL'),
                    auth_mode=HttpAuthMode.TOKEN,
                    token=configuration.require('METEODATA_TOKEN'),
                    connect_timeout_seconds=_positive_int(configuration, 'METEODATA_CONNECT_TIMEOUT_SECONDS'),
                    read_timeout_seconds=_positive_int(configuration, 'METEODATA_READ_TIMEOUT_SECONDS'),
                    write_timeout_seconds=_positive_int(configuration, 'METEODATA_WRITE_TIMEOUT_SECONDS'),
                    pool_timeout_seconds=_positive_int(configuration, 'METEODATA_POOL_TIMEOUT_SECONDS'),
                    max_response_bytes=_positive_int(configuration, 'METEODATA_MAX_RESPONSE_BYTES'),
                    verify_tls=_bool(configuration, 'METEODATA_VERIFY_TLS'),
                    allow_insecure_http=False,
                ),
                lookback_minutes=_positive_int(configuration, 'METEODATA_LOOKBACK_MINUTES'),
                retry_delay_seconds=_non_negative_int(configuration, 'METEODATA_RETRY_DELAY_SECONDS'),
            )
        except (ConfigurationValueError, HttpConfigurationError) as error:
            raise MeteodataProcessConfigurationError('invalid Meteodata process configuration') from error


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='METEODATA_BASE_URL'),
        ConfigurationVariableSpec(key='METEODATA_TOKEN', sensitive=True),
        ConfigurationVariableSpec(key='METEODATA_CONNECT_TIMEOUT_SECONDS', default='5'),
        ConfigurationVariableSpec(key='METEODATA_READ_TIMEOUT_SECONDS', default='15'),
        ConfigurationVariableSpec(key='METEODATA_WRITE_TIMEOUT_SECONDS', default='15'),
        ConfigurationVariableSpec(key='METEODATA_POOL_TIMEOUT_SECONDS', default='5'),
        ConfigurationVariableSpec(key='METEODATA_MAX_RESPONSE_BYTES', default='2097152'),
        ConfigurationVariableSpec(key='METEODATA_VERIFY_TLS', default='true'),
        ConfigurationVariableSpec(key='METEODATA_LOOKBACK_MINUTES', default='90'),
        ConfigurationVariableSpec(key='METEODATA_RETRY_DELAY_SECONDS', default='60'),
        ConfigurationVariableSpec(
            key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'
        ),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(
            key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE',
            required=False,
        ),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING',
            required=False,
            sensitive=True,
        ),
    )


def _positive_int(configuration: ResolvedConfiguration, key: str) -> int:
    value = configuration.get_int(key)
    if value is None or value <= 0:
        raise MeteodataProcessConfigurationError(f'{key} must be greater than zero')
    return value


def _non_negative_int(configuration: ResolvedConfiguration, key: str) -> int:
    value = configuration.get_int(key)
    if value is None or value < 0:
        raise MeteodataProcessConfigurationError(f'{key} must be zero or greater')
    return value


def _bool(configuration: ResolvedConfiguration, key: str) -> bool:
    value = configuration.get_bool(key)
    if value is None:
        raise MeteodataProcessConfigurationError(f'{key} must be a boolean')
    return value
