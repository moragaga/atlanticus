from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.alarm_materialization.errors import AlarmMaterializationSettingsError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosConfigurationError, CosmosSettings

COSMOS_ENDPOINT_VARIABLE = 'ADA_COMMAND_CENTER_COSMOS_ENDPOINT'
COSMOS_KEY_VARIABLE = 'ADA_COMMAND_CENTER_COSMOS_KEY'
COSMOS_DATABASE_VARIABLE = 'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME'
POLL_INTERVAL_VARIABLE = 'ALARM_MATERIALIZATION_POLL_SECONDS'


@dataclass(frozen=True, slots=True)
class AlarmMaterializationSettings:
    cosmos: CosmosSettings
    poll_interval_seconds: float

    @classmethod
    def from_configuration(
        cls,
        configuration: ResolvedConfiguration,
    ) -> AlarmMaterializationSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        try:
            cosmos = CosmosSettings(
                endpoint=configuration.require(COSMOS_ENDPOINT_VARIABLE),
                key=configuration.require(COSMOS_KEY_VARIABLE),
                database_name=configuration.require(COSMOS_DATABASE_VARIABLE),
                allow_insecure_http=configuration.environment.is_local,
            )
        except CosmosConfigurationError as error:
            raise AlarmMaterializationSettingsError(str(error)) from error


        poll_interval_seconds = _positive_float(
            configuration.require(POLL_INTERVAL_VARIABLE),
            POLL_INTERVAL_VARIABLE,
        )
        return cls(
            cosmos=cosmos,
            poll_interval_seconds=poll_interval_seconds,
        )


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
        ConfigurationVariableSpec(key='ATLANTICUS_JOB_EXECUTION_DISABLED', default='false'),
        ConfigurationVariableSpec(key=COSMOS_ENDPOINT_VARIABLE),
        ConfigurationVariableSpec(key=COSMOS_KEY_VARIABLE, sensitive=True),
        ConfigurationVariableSpec(key=COSMOS_DATABASE_VARIABLE),
        ConfigurationVariableSpec(key=POLL_INTERVAL_VARIABLE, default='30'),
        ConfigurationVariableSpec(
            key='ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED',
            default='true',
        ),
        ConfigurationVariableSpec(
            key='ATLANTICUS_AZURE_OBSERVABILITY_MODE',
            default='off',
        ),
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




def _positive_float(value: str, name: str) -> float:
    try:
        resolved = float(value)
    except ValueError as error:
        raise AlarmMaterializationSettingsError(f'{name} must contain a positive number') from error
    if not math.isfinite(resolved) or resolved <= 0:
        raise AlarmMaterializationSettingsError(f'{name} must contain a positive number')
    return resolved
