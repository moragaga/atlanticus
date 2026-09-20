from __future__ import annotations

import pytest

from ada.processes.kpi_historian.errors import KpiHistorianConfigurationError
from ada.processes.kpi_historian.settings import KpiHistorianSettings, configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path, **overrides) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-historian-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'KPI_HISTORIAN_POLL_INTERVAL_SECONDS': '1',
        'REPROCESS_CURRENT': 'false',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    values.update(overrides)
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_resolve_upstream_application_poll_interval_and_reprocess_default(
    tmp_path,
) -> None:
    settings = KpiHistorianSettings.from_configuration(_configuration(tmp_path))

    assert settings.kpi_runtime_application == 'ada-kpi-runtime-local'
    assert settings.poll_interval_seconds == 1
    assert settings.reprocess_current is False


def test_settings_accept_reprocess_current_true(tmp_path) -> None:
    settings = KpiHistorianSettings.from_configuration(
        _configuration(tmp_path, REPROCESS_CURRENT='true')
    )

    assert settings.reprocess_current is True


def test_settings_reject_invalid_reprocess_current(tmp_path) -> None:
    with pytest.raises(KpiHistorianConfigurationError, match='must be true or false'):
        KpiHistorianSettings.from_configuration(_configuration(tmp_path, REPROCESS_CURRENT='yes'))


def test_configuration_spec_defaults_reprocess_current_to_false() -> None:
    spec = next(spec for spec in configuration_specs() if spec.key == 'REPROCESS_CURRENT')

    assert spec.default == 'false'


def test_settings_reject_non_positive_poll_interval(tmp_path) -> None:
    with pytest.raises(KpiHistorianConfigurationError, match='positive number'):
        KpiHistorianSettings.from_configuration(
            _configuration(tmp_path, KPI_HISTORIAN_POLL_INTERVAL_SECONDS='0')
        )
