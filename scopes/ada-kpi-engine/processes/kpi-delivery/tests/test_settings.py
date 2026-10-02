import pytest

from ada.processes.kpi_delivery.errors import KpiDeliveryConfigurationError
from ada.processes.kpi_delivery.settings import (
    KpiDeliveryProcessSettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, interval='1', workers='2'):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'POLL_INTERVAL_SECONDS': interval,
        'KPI_DELIVERY_MAX_WORKERS': workers,
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_use_generic_runtime_poll_and_delivery_worker_pool(tmp_path):
    settings = KpiDeliveryProcessSettings.from_configuration(_configuration(tmp_path))
    keys = {spec.key for spec in configuration_specs()}

    assert settings.kpi_runtime_application == 'ada-kpi-runtime-local'
    assert settings.poll_interval_seconds == 1
    assert settings.max_workers == 2
    assert 'POLL_INTERVAL_SECONDS' in keys
    assert 'KPI_DELIVERY_MAX_WORKERS' in keys
    assert all('COSMOS' not in key for key in keys)


def test_settings_allow_zero_poll_but_require_positive_workers(tmp_path):
    assert (
        KpiDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, interval='0')
        ).poll_interval_seconds
        == 0
    )

    with pytest.raises(KpiDeliveryConfigurationError, match='non-negative'):
        KpiDeliveryProcessSettings.from_configuration(_configuration(tmp_path, interval='-1'))

    with pytest.raises(KpiDeliveryConfigurationError, match='positive integer'):
        KpiDeliveryProcessSettings.from_configuration(_configuration(tmp_path, workers='0'))
