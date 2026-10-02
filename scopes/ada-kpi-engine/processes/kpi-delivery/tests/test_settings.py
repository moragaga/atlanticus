from __future__ import annotations

import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from ada.processes.kpi_delivery.settings import KpiDeliveryProcessSettings, configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, **overrides) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'COSMOS_CONSUMPTION_ENDPOINT': 'http://localhost:8081',
        'COSMOS_CONSUMPTION_KEY': 'local-key',
        'COSMOS_CONSUMPTION_DATABASE_NAME': 'ada',
        'KPI_DELIVERY_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    values.update(overrides)
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_keep_database_external_and_container_contract_internal(tmp_path) -> None:
    settings = KpiDeliveryProcessSettings.from_configuration(_configuration(tmp_path))
    keys = {spec.key for spec in configuration_specs()}

    assert settings.kpi_runtime_application == 'ada-kpi-runtime-local'
    assert settings.poll_interval_seconds == 1
    assert settings.cosmos.database_name == 'ada'
    assert 'KPI_DELIVERY_CONFIGURATION_CONTAINER' not in keys
    assert 'KPI_DELIVERY_CONFIGURATION_ITEM_ID' not in keys
    assert 'KPI_DELIVERY_CONFIGURATION_PARTITION_KEY' not in keys
    assert 'KPI_LATEST_DELIVERY_CONTAINER' not in keys


def test_settings_reject_non_positive_poll_interval(tmp_path) -> None:
    with pytest.raises(KpiDeliveryConfigurationError, match='positive number'):
        KpiDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, KPI_DELIVERY_POLL_INTERVAL_SECONDS='0')
        )
