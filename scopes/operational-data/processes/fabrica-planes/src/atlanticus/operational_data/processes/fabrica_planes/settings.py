from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.storage import StorageSasCredential, StorageSettings
from atlanticus.data_producers.fabrica import FabricaStorageConnection
from atlanticus.operational_data.processes.fabrica_planes.errors import (
    FabricaProcessConfigurationError,
)

STORAGE_SUFFIX = 'FABRICA_PLANES'


@dataclass(frozen=True, slots=True)
class FabricaProcessSettings:
    connection: FabricaStorageConnection
    idle_seconds: int = 5

    @classmethod
    def from_configuration(cls, configuration: ResolvedConfiguration) -> FabricaProcessSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise FabricaProcessConfigurationError('configuration must be a ResolvedConfiguration')
        url_key = f'STORAGE_ACCOUNT_SAS_URL_{STORAGE_SUFFIX}'
        token_key = f'STORAGE_ACCOUNT_SAS_TOKEN_{STORAGE_SUFFIX}'
        parsed = urlsplit(configuration.require(url_key).strip())
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise FabricaProcessConfigurationError(
                f'{url_key} must be an absolute HTTP or HTTPS URL'
            )
        container = tuple(part for part in parsed.path.split('/') if part)
        if len(container) != 1:
            raise FabricaProcessConfigurationError(f'{url_key} must identify exactly one container')
        url_token = parsed.query.strip().lstrip('?')
        configured_token = str(configuration.values.get(token_key) or '').strip().lstrip('?')
        if url_token and configured_token and url_token != configured_token:
            raise FabricaProcessConfigurationError(
                f'{url_key} and {token_key} contain different SAS tokens'
            )
        token = configured_token or url_token
        if not token:
            raise FabricaProcessConfigurationError(
                f'{token_key} is required when {url_key} has no query'
            )
        try:
            settings = StorageSettings(
                credential=StorageSasCredential(
                    account_url=urlunsplit((parsed.scheme, parsed.netloc, '', '', '')),
                    sas_token=token,
                    allow_insecure_http=parsed.scheme == 'http',
                )
            )
        except Exception as error:
            raise FabricaProcessConfigurationError(str(error)) from error
        raw_idle = configuration.require('FABRICA_IDLE_SECONDS')
        try:
            idle = int(raw_idle)
        except TypeError, ValueError:
            raise FabricaProcessConfigurationError(
                'FABRICA_IDLE_SECONDS must be a positive integer'
            ) from None
        if idle <= 0:
            raise FabricaProcessConfigurationError(
                'FABRICA_IDLE_SECONDS must be a positive integer'
            )
        return cls(
            connection=FabricaStorageConnection(settings=settings, container_name=container[0]),
            idle_seconds=idle,
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key=f'STORAGE_ACCOUNT_SAS_URL_{STORAGE_SUFFIX}', sensitive=True),
        ConfigurationVariableSpec(
            key=f'STORAGE_ACCOUNT_SAS_TOKEN_{STORAGE_SUFFIX}', required=False, sensitive=True
        ),
        ConfigurationVariableSpec(key='FABRICA_IDLE_SECONDS', default='5'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
