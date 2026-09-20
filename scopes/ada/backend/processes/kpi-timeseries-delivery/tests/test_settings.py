from __future__ import annotations

from ada.processes.kpi_timeseries_delivery.settings import (
    KpiTimeseriesDeliveryProcessSettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-timeseries-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_HISTORIAN_APPLICATION': 'ada-kpi-historian-local',
        'COSMOS_CONSUMPTION_ENDPOINT': 'http://localhost:8081',
        'COSMOS_CONSUMPTION_KEY': 'local-key',
        'COSMOS_CONSUMPTION_DATABASE_NAME': 'ada',
        'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_keep_database_external_and_container_contract_internal(tmp_path) -> None:
    settings = KpiTimeseriesDeliveryProcessSettings.from_configuration(_configuration(tmp_path))
    keys = {spec.key for spec in configuration_specs()}

    assert settings.historian_application == 'ada-kpi-historian-local'
    assert settings.cosmos.database_name == 'ada'
    assert 'KPI_DELIVERY_CONFIGURATION_CONTAINER' not in keys
    assert 'KPI_DELIVERY_CONFIGURATION_ITEM_ID' not in keys
    assert 'KPI_DELIVERY_CONFIGURATION_PARTITION_KEY' not in keys
    assert 'KPI_TIMESERIES_DELIVERY_CONTAINER' not in keys
