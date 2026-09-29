from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

# Source Key viene de un contrato estable; no de configuración del desarrollador.
from ada_command_center.domain.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.web.alarms.projection.cosmos import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
)
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosConfigurationError, CosmosSettings


class AlarmMaterializationSettingsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmMaterializationSettings:
    cosmos: CosmosSettings
    volume_path: Path
    qualification_file: Path
    poll_interval_seconds: float

    # El nombre físico está fijado por el mismo contrato que usa el host Web.
    @property
    def source_key(self) -> str:
        return ALARM_CONFIGURATION_SOURCE_KEY

    @property
    def projection_container(self) -> str:
        return ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.default_physical_name

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
        # VOLUMEN_PATH conserva selección manual del operador por entorno.
        volume = Path(configuration.require('VOLUMEN_PATH')).expanduser()
        if not volume.is_absolute():
            raise AlarmMaterializationSettingsError('VOLUMEN_PATH must be absolute')
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
            volume_path=volume,
            qualification_file=path,
            poll_interval_seconds=interval,
        )


# No aceptar Source Key ni contenedor físico por .env: evita divergencia silenciosa.
def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ALARM_COSMOS_ENDPOINT'),
        ConfigurationVariableSpec(key='ALARM_COSMOS_KEY', sensitive=True),
        ConfigurationVariableSpec(key='ALARM_COSMOS_DATABASE_NAME'),
        ConfigurationVariableSpec(key='ALARM_QUALIFICATIONS_FILE'),
        ConfigurationVariableSpec(key='ALARM_MATERIALIZATION_POLL_SECONDS', default='30'),
        ConfigurationVariableSpec(key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED', default='true'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_MODE', default='off'),
        ConfigurationVariableSpec(key='ATLANTICUS_AZURE_OBSERVABILITY_PROFILE', required=False),
        ConfigurationVariableSpec(
            key='APPLICATION_INSIGHTS_CONNECTION_STRING', required=False, sensitive=True
        ),
    )
