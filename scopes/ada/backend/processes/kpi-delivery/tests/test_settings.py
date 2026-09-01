from __future__ import annotations

import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from ada.processes.kpi_delivery.settings import KpiDeliveryProcessSettings
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
        'KPI_DELIVERY_CONFIGURATION_CONTAINER': 'config',
        'KPI_DELIVERY_CONFIGURATION_ITEM_ID': 'kpis',
        'KPI_DELIVERY_CONFIGURATION_PARTITION_KEY': 'kpis',
        'KPI_LATEST_DELIVERY_CONTAINER': 'latest',
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


def test_settings_resolve_named_cosmos_and_upstream_application(tmp_path) -> None:
    settings = KpiDeliveryProcessSettings.from_configuration(_configuration(tmp_path))

    assert settings.kpi_runtime_application == 'ada-kpi-runtime-local'
    assert settings.configuration_container == 'config'
    assert settings.latest_container == 'latest'
    assert settings.poll_interval_seconds == 1
    assert settings.cosmos.database_name == 'ada'


def test_settings_reject_non_positive_poll_interval(tmp_path) -> None:
    with pytest.raises(KpiDeliveryConfigurationError, match='positive number'):
        KpiDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, KPI_DELIVERY_POLL_INTERVAL_SECONDS='0')
        )
