from __future__ import annotations

import math
from dataclasses import dataclass

from ada.processes.kpi_materialization.errors import KpiMaterializationSettingsError
from atlanticus.configuration import ConfigurationVariableSpec, ResolvedConfiguration

POLL_INTERVAL_VARIABLE = 'KPI_MATERIALIZATION_POLL_SECONDS'


@dataclass(frozen=True, slots=True)
class KpiMaterializationSettings:
    poll_interval_seconds: float

    @classmethod
    def from_configuration(
        cls,
        configuration: ResolvedConfiguration,
    ) -> KpiMaterializationSettings:
        if not isinstance(configuration, ResolvedConfiguration):
            raise TypeError('configuration must be a ResolvedConfiguration')
        try:
            interval = float(configuration.require(POLL_INTERVAL_VARIABLE))
        except (TypeError, ValueError) as error:
            raise KpiMaterializationSettingsError(
                f'{POLL_INTERVAL_VARIABLE} must contain a positive number'
            ) from error
        if not math.isfinite(interval) or interval <= 0:
            raise KpiMaterializationSettingsError(
                f'{POLL_INTERVAL_VARIABLE} must contain a positive number'
            )
        return cls(poll_interval_seconds=interval)


def configuration_specs() -> tuple[ConfigurationVariableSpec, ...]:
    return (
        ConfigurationVariableSpec(key='APPLICATION'),
        ConfigurationVariableSpec(key='VOLUMEN_PATH'),
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
