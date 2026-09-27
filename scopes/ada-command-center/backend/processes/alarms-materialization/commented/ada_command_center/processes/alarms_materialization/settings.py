# Declara configuración de entrada, salida, evidence y cadencia sin nombres físicos inventados.
# Usa el esquema ConfigurationBootstrap del proyecto y CosmosSettings para validación segura.
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosConfigurationError, CosmosSettings


# Contrato AlarmMaterializationSettingsError: mantiene invariantes de esta frontera.
class AlarmMaterializationSettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
# Contrato AlarmMaterializationSettings: mantiene invariantes de esta frontera.
class AlarmMaterializationSettings:
    cosmos: CosmosSettings
    source_key: str
    projection_container: str
    output_container: str
    qualification_file: Path
    poll_interval_seconds: float

    @classmethod
    def from_configuration(
        cls, configuration: ResolvedConfiguration
    ) -> AlarmMaterializationSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        try:
            cosmos = CosmosSettings(
                endpoint=configuration.require('ALARM_COSMOS_ENDPOINT'),
                key=configuration.require('ALARM_COSMOS_KEY'),
                database_name=configuration.require('ALARM_COSMOS_DATABASE_NAME'),
                allow_insecure_http=configuration.environment.is_local,
            )
        except CosmosConfigurationError as error:
            raise AlarmMaterializationSettingsError(str(error)) from error
        path = Path(configuration.require('ALARM_QUALIFICATIONS_FILE')).expanduser()
        if not path.is_absolute():
            raise AlarmMaterializationSettingsError('ALARM_QUALIFICATIONS_FILE must be absolute')
        try:
            interval = float(configuration.require('ALARM_MATERIALIZATION_POLL_SECONDS'))
        except ValueError as error:
            raise AlarmMaterializationSettingsError(
                'ALARM_MATERIALIZATION_POLL_SECONDS must be a positive number'
            ) from error
        if not math.isfinite(interval) or interval <= 0:
            raise AlarmMaterializationSettingsError(
                'ALARM_MATERIALIZATION_POLL_SECONDS must be a positive number'
            )
        return cls(
            cosmos=cosmos,
            source_key=_required(configuration.require('ALARM_CONFIGURATION_SOURCE_KEY')),
            projection_container=_required(configuration.require('ALARM_PROJECTION_CONTAINER')),
            output_container=_required(
                configuration.require('ALARM_MATERIALIZATION_OUTPUT_CONTAINER')
            ),
            qualification_file=path,
            poll_interval_seconds=interval,
        )


# Operación _required: mantiene invariantes de esta frontera.
def _required(value: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlarmMaterializationSettingsError(
            'Alarm Materialization setting must be non-empty text'
        )
    return value


# Operación configuration_specs: mantiene invariantes de esta frontera.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_COSMOS_ENDPOINT'),
        ConfigurationVariableSpec(key='ALARM_COSMOS_KEY', sensitive=True),
        ConfigurationVariableSpec(key='ALARM_COSMOS_DATABASE_NAME'),
        ConfigurationVariableSpec(key='ALARM_CONFIGURATION_SOURCE_KEY'),
        ConfigurationVariableSpec(key='ALARM_PROJECTION_CONTAINER'),
        ConfigurationVariableSpec(key='ALARM_MATERIALIZATION_OUTPUT_CONTAINER'),
        ConfigurationVariableSpec(key='ALARM_QUALIFICATIONS_FILE'),
        ConfigurationVariableSpec(key='ALARM_MATERIALIZATION_POLL_SECONDS', default='30'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
