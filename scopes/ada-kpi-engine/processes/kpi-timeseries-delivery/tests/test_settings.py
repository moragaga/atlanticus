from __future__ import annotations

import pytest

from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryConfigurationError,
)
from ada.processes.kpi_timeseries_delivery.settings import (
    KpiTimeseriesDeliveryProcessSettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, interval='1', workers='2'):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-timeseries-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_HISTORIAN_APPLICATION': 'ada-kpi-historian-local',
        'KPI_TIMESERIES_DELIVERY_POLL_INTERVAL_SECONDS': interval,
        'KPI_TIMESERIES_DELIVERY_MAX_WORKERS': workers,
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_use_historian_poll_and_worker_pool_without_cosmos_variables(tmp_path):
    settings = KpiTimeseriesDeliveryProcessSettings.from_configuration(_configuration(tmp_path))
    keys = {spec.key for spec in configuration_specs()}

    assert settings.historian_application == 'ada-kpi-historian-local'
    assert settings.poll_interval_seconds == 1
    assert settings.max_workers == 2
    assert 'KPI_TIMESERIES_DELIVERY_MAX_WORKERS' in keys
    assert all('COSMOS' not in key for key in keys)


def test_settings_allow_zero_poll_but_require_positive_workers(tmp_path):
    assert (
        KpiTimeseriesDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, interval='0')
        ).poll_interval_seconds
        == 0
    )

    with pytest.raises(KpiTimeseriesDeliveryConfigurationError, match='non-negative'):
        KpiTimeseriesDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, interval='-1')
        )

    with pytest.raises(
        KpiTimeseriesDeliveryConfigurationError,
        match='positive integer',
    ):
        KpiTimeseriesDeliveryProcessSettings.from_configuration(
            _configuration(tmp_path, workers='0')
        )
