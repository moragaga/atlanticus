from __future__ import annotations

import pytest

from ada.processes.kpi_runtime.errors import KpiRuntimeConfigurationError
from ada.processes.kpi_runtime.settings import KpiRuntimeSettings, configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment
from atlanticus.operational_data.sources import PiSourceProvider


def _configuration(**overrides: str) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-runtime-local',
        'VOLUMEN_PATH': '/tmp/atlanticus',
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'operational-data-notpii-local',
        'KPI_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    values.update(overrides)
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_accept_notpii_and_optional_routes() -> None:
    settings = KpiRuntimeSettings.from_configuration(
        _configuration(DISPATCH_APPLICATION='operational-data-dispatch')
    )

    assert settings.pi_source is PiSourceProvider.NOTPII
    assert settings.pi_application == 'operational-data-notpii-local'
    assert settings.dispatch_application == 'operational-data-dispatch'
    assert settings.poll_interval_seconds == 1


def test_settings_accept_pi_web_api_alias() -> None:
    settings = KpiRuntimeSettings.from_configuration(_configuration(PI_SOURCE='PI_WEB_API'))

    assert settings.pi_source is PiSourceProvider.PI_WEB_API


def test_invalid_pi_source_is_rejected() -> None:
    with pytest.raises(KpiRuntimeConfigurationError, match='NOTPII or PI_WEB_API'):
        KpiRuntimeSettings.from_configuration(_configuration(PI_SOURCE='other'))


def test_poll_interval_must_be_positive() -> None:
    with pytest.raises(KpiRuntimeConfigurationError, match='positive number'):
        KpiRuntimeSettings.from_configuration(_configuration(KPI_POLL_INTERVAL_SECONDS='0'))


def test_configuration_specs_do_not_declare_business_secrets() -> None:
    specs = configuration_specs()
    keys = {spec.key for spec in specs}

    assert 'APPLICATION' in keys
    assert 'VOLUMEN_PATH' in keys
    assert 'PI_SOURCE' in keys
    assert 'PI_APPLICATION' in keys
    assert 'APPLICATION_INSIGHTS_CONNECTION_STRING' in keys
