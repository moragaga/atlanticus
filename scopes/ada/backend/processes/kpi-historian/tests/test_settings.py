from __future__ import annotations

import pytest

from ada.processes.kpi_historian.errors import KpiHistorianConfigurationError
from ada.processes.kpi_historian.settings import KpiHistorianSettings
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, **overrides) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-historian-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'KPI_HISTORIAN_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    values.update(overrides)
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_resolve_upstream_application_and_poll_interval(tmp_path) -> None:
    settings = KpiHistorianSettings.from_configuration(_configuration(tmp_path))

    assert settings.kpi_runtime_application == 'ada-kpi-runtime-local'
    assert settings.poll_interval_seconds == 1


def test_settings_reject_non_positive_poll_interval(tmp_path) -> None:
    with pytest.raises(KpiHistorianConfigurationError, match='positive number'):
        KpiHistorianSettings.from_configuration(
            _configuration(tmp_path, KPI_HISTORIAN_POLL_INTERVAL_SECONDS='0')
        )
