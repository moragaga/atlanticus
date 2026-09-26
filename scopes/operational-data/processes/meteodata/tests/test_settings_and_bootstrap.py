from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.connectivity.http import HttpAuthMode
from atlanticus.operational_data.processes.meteodata.bootstrap import load_configuration
from atlanticus.operational_data.processes.meteodata.settings import MeteodataSettings, configuration_specs


def values(tmp_path):
    return {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-meteodata-local',
        'VOLUMEN_PATH': str(tmp_path),
        'METEODATA_BASE_URL': 'https://pelambres.meteodata.cl/met/',
        'METEODATA_TOKEN': 'never-log-this-test-token',
    }


def test_process_resolves_token_and_safe_defaults(tmp_path):
    env = values(tmp_path)
    config = ConfigurationBootstrap.from_process(
        specs=configuration_specs(), process_values=env,
    ).load(process_values=env)
    settings = MeteodataSettings.from_configuration(config)
    assert settings.http.auth_mode is HttpAuthMode.TOKEN
    assert settings.http.token == env['METEODATA_TOKEN']
    assert 'never-log-this-test-token' not in repr(settings)
    assert settings.lookback_minutes == 90
    assert settings.retry_delay_seconds == 60
    assert settings.http.verify_tls is True
    assert settings.http.allow_insecure_http is False


def test_projection_does_not_require_a_timestamp_mode_setting(tmp_path):
    env = values(tmp_path)
    config = load_configuration(process_root=tmp_path, environ=env)
    settings = MeteodataSettings.from_configuration(config)
    assert settings.http.token == env['METEODATA_TOKEN']
    assert 'METEODATA_PROJECTION_TIMESTAMP_MODE' not in {spec.key for spec in configuration_specs()}


def test_bootstrap_local_loads_env_and_never_requires_key_vault(tmp_path):
    env = values(tmp_path)
    (tmp_path / '.env').write_text(
        '\n'.join(f'{key}={value}' for key, value in env.items()) + '\n', encoding='utf-8'
    )
    config = load_configuration(process_root=tmp_path, environ={})
    assert config.require('METEODATA_TOKEN') == env['METEODATA_TOKEN']


def test_config_specs_explicitly_mark_credentials_sensitive():
    specs = {spec.key: spec for spec in configuration_specs()}
    assert specs['METEODATA_TOKEN'].sensitive is True
    assert 'METEODATA_PROJECTION_TIMESTAMP_MODE' not in specs
    assert specs['METEODATA_LOOKBACK_MINUTES'].default == '90'
