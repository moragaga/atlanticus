from __future__ import annotations

import pytest

from atlanticus.observability_azure import (
    AzureObservabilityConfigurationError,
    AzureObservabilityMode,
    AzureObservabilityProfile,
    AzureObservabilitySettings,
)


def test_defaults_are_off_and_slim() -> None:
    settings = AzureObservabilitySettings.from_sources(environ={})

    assert settings.mode is AzureObservabilityMode.OFF
    assert settings.profile is AzureObservabilityProfile.SLIM
    assert not settings.tracing_enabled


def test_export_requires_the_global_connection_string() -> None:
    with pytest.raises(AzureObservabilityConfigurationError, match='required'):
        AzureObservabilitySettings.from_sources(
            environ={'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export'}
        )


def test_diagnostic_export_enables_tracing_without_exposing_secret() -> None:
    secret = 'InstrumentationKey=secret'
    settings = AzureObservabilitySettings.from_sources(
        environ={
            'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
            'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
            'APPLICATION_INSIGHTS_CONNECTION_STRING': secret,
        }
    )

    assert settings.tracing_enabled
    assert secret not in repr(settings)


@pytest.mark.parametrize('mode', ['off', 'preview'])
def test_non_export_modes_do_not_read_connection_string(mode) -> None:
    class _Environment(dict):
        def get(self, key, default=None):
            if key == 'APPLICATION_INSIGHTS_CONNECTION_STRING':
                raise AssertionError('connection string must not be read')
            return super().get(key, default)

    settings = AzureObservabilitySettings.from_sources(
        environ=_Environment({'ATLANTICUS_AZURE_OBSERVABILITY_MODE': mode})
    )

    assert settings.connection_string is None


@pytest.mark.parametrize(
    ('environ', 'message'),
    [
        ({'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'invalid'}, 'must be one of'),
        ({'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 1}, 'must be a string'),
    ],
)
def test_invalid_environment_configuration_is_rejected(environ, message) -> None:
    with pytest.raises(AzureObservabilityConfigurationError, match=message):
        AzureObservabilitySettings.from_sources(environ=environ)
