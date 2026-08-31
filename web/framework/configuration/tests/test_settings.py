from pathlib import Path

import pytest
from pydantic import ValidationError

from atlanticus.web.configuration import WebEnvironment, WebSettings


def test_web_settings_default_to_local_without_optional_telemetry(monkeypatch):
    for name in (
        'ATLANTICUS_ENVIRONMENT',
        'APPLICATION_INSIGHTS_CONNECTION_STRING',
    ):
        monkeypatch.delenv(name, raising=False)

    settings = WebSettings()

    assert settings.environment is WebEnvironment.LOCAL
    assert settings.application_insights_connection_string is None


def test_web_settings_read_and_normalize_supported_environment_variables():
    settings = WebSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': ' PRODUCTION ',
            'APPLICATION_INSIGHTS_CONNECTION_STRING': ' InstrumentationKey=test ',
        }
    )

    assert settings.environment is WebEnvironment.PRODUCTION
    assert settings.environment.is_production is True
    assert settings.application_insights_connection_string == 'InstrumentationKey=test'


def test_web_settings_treat_blank_application_insights_as_not_configured():
    settings = WebSettings.from_mapping({'APPLICATION_INSIGHTS_CONNECTION_STRING': '   '})

    assert settings.application_insights_connection_string is None


def test_web_settings_ignore_unrelated_backend_and_hosting_environment_variables():
    settings = WebSettings.from_mapping(
        {
            'ENVIRONMENT': 'prd',
            'COSMOS_KEY': 'secret',
            'ATLANTICUS_WEB_WORKERS': '99',
            'ATLANTICUS_WEB_THREADS': '99',
            'ATLANTICUS_ENVIRONMENT': 'local',
        }
    )

    assert settings.environment is WebEnvironment.LOCAL
    assert not hasattr(settings, 'cosmos_key')
    assert not hasattr(settings, 'workers')
    assert not hasattr(settings, 'threads')


def test_web_settings_reject_unknown_environment():
    with pytest.raises(ValidationError):
        WebSettings.from_mapping({'ATLANTICUS_ENVIRONMENT': 'dev'})


def test_from_mapping_snapshots_values():
    values = {'ATLANTICUS_ENVIRONMENT': 'production'}
    settings = WebSettings.from_mapping(values)

    values['ATLANTICUS_ENVIRONMENT'] = 'local'

    assert settings.environment is WebEnvironment.PRODUCTION


def test_from_mapping_requires_text_keys_and_values():
    with pytest.raises(TypeError, match='Environment variable names must be text'):
        WebSettings.from_mapping({1: 'value'})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Environment variable 'VALUE' must contain text"):
        WebSettings.from_mapping({'VALUE': 1})  # type: ignore[dict-item]


def test_web_settings_do_not_implicitly_load_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    Path('.env').write_text('ATLANTICUS_ENVIRONMENT=production\n', encoding='utf-8')

    settings = WebSettings()

    assert settings.environment is WebEnvironment.LOCAL
