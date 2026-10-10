from __future__ import annotations

import json

import pytest

import ada.processes.alarm_historian.composition as composition_module
from ada.processes.alarm_historian.bootstrap import load_configuration, run
from ada.processes.alarm_historian.composition import build_composition
from ada.processes.alarm_historian.settings import (
    AlarmHistorianSettingsError,
    configuration_specs,
)


def _environment(tmp_path, *, producer='alarm-runtime-local', max_records='3'):
    return {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'alarm-historian-local',
        'VOLUMEN_PATH': str(tmp_path),
        'ALARM_RUNTIME_APPLICATION': producer,
        'ALARM_HISTORIAN_MAX_RECORDS': max_records,
    }


def test_configuration_and_composition_wire_isolated_output_roots(tmp_path):
    config = load_configuration(process_root=tmp_path, environ=_environment(tmp_path))
    composition = build_composition(configuration=config)
    assert composition.settings.stream_id == 'alarm-runtime-local'
    assert composition.settings.producer_application == 'alarm-runtime-local'
    assert composition.settings.max_records == 3
    assert composition.definition.job_key == 'alarm-historian'
    assert composition.definition.run_once


def test_entrypoint_passes_resolved_configuration_to_runtime(tmp_path, monkeypatch):
    called = []

    def execute_job(*, definition, iteration, argv, environ):
        called.append((definition, iteration, argv, environ))
        return 'executed'

    monkeypatch.setattr(composition_module, 'execute_job', execute_job)
    args = []
    result = run(process_root=tmp_path, environ=_environment(tmp_path), argv=args)
    assert result == 'executed'
    assert len(called) == 1
    definition, iteration, received_args, environ = called[0]
    assert definition.service_name == 'alarm-historian'
    assert callable(iteration)
    assert received_args == args
    assert environ['ALARM_RUNTIME_APPLICATION'] == 'alarm-runtime-local'


@pytest.mark.parametrize('producer,max_records', [
    ('../bad', '10'),
    (' ', '10'),
    (' alarm-runtime-local', '10'),
    ('alarm-runtime-local', '0'),
    ('alarm-runtime-local', '-5'),
    ('alarm-runtime-local', '10001'),
    ('alarm-runtime-local', '02'),
])
def test_rejects_invalid_source_identity_or_batch_limit(tmp_path, producer, max_records):
    env = _environment(tmp_path, producer=producer, max_records=max_records)
    configuration = load_configuration(process_root=tmp_path, environ=env)
    with pytest.raises(AlarmHistorianSettingsError):
        build_composition(configuration=configuration)


def test_local_dotenv_can_configure_process_without_environment_override(tmp_path):
    content = '\n'.join(f'{key}={value}' for key, value in _environment(tmp_path).items())
    (tmp_path / '.env').write_text(content)
    config = load_configuration(process_root=tmp_path, environ={})
    assert config.require('ALARM_RUNTIME_APPLICATION') == 'alarm-runtime-local'


def test_deployed_configuration_reads_manifest_and_ignores_runtime_overrides(tmp_path):
    values = _environment(tmp_path)
    manifest = [
        {'var_name': key, 'secret_name': None, 'value': value, 'exists_in_key_vault': False}
        for key, value in values.items() if key != 'ENVIRONMENT'
    ]
    (tmp_path / 'secrets.json').write_text(json.dumps(manifest))
    config = load_configuration(
        process_root=tmp_path,
        environ={'ENVIRONMENT': 'dev', 'APPLICATION': 'wrong-process-name'},
    )
    assert config.require('APPLICATION') == 'alarm-historian-local'
    assert config.require('ALARM_RUNTIME_APPLICATION') == 'alarm-runtime-local'
    assert build_composition(configuration=config).settings.stream_id == 'alarm-runtime-local'


def test_runtime_application_is_the_only_external_source_identity(tmp_path):
    keys = {spec.key for spec in configuration_specs()}
    assert 'ALARM_RUNTIME_APPLICATION' in keys
    assert 'ALARM_HISTORIAN_STREAM_ID' not in keys
    assert 'ALARM_HISTORIAN_PRODUCER_APPLICATION' not in keys

    configuration = load_configuration(
        process_root=tmp_path,
        environ=_environment(tmp_path, producer='runtime-two'),
    )
    settings = build_composition(configuration=configuration).settings
    assert settings.stream_id == 'runtime-two'
    assert settings.producer_application == 'runtime-two'


def test_invalid_volume_fails_before_any_output_is_created(tmp_path):
    environ = _environment(tmp_path)
    environ['VOLUMEN_PATH'] = 'relative/path'
    with pytest.raises(AlarmHistorianSettingsError, match='absolute'):
        run(process_root=tmp_path, environ=environ)
    assert not list(tmp_path.iterdir())


def test_key_vault_resolution_is_only_used_when_manifest_requests_a_secret(
    tmp_path, monkeypatch
):
    import ada.processes.alarm_historian.bootstrap as bootstrap_module

    manifest = [
        {'var_name': key, 'secret_name': None, 'value': value, 'exists_in_key_vault': False}
        for key, value in _environment(tmp_path).items() if key != 'ENVIRONMENT'
    ]
    manifest.extend([
        {'var_name': 'COMPANY_ABREV', 'secret_name': None, 'value': 'ada',
         'exists_in_key_vault': False},
        {'var_name': 'PRODUCT_ABREV', 'secret_name': None, 'value': 'op',
         'exists_in_key_vault': False},
        {'var_name': 'APPLICATION_INSIGHTS_CONNECTION_STRING',
         'secret_name': 'insights-secret', 'value': None, 'exists_in_key_vault': True},
    ])
    (tmp_path / 'secrets.json').write_text(json.dumps(manifest))
    calls = []

    class Resolver:
        def __init__(self, *, settings):
            calls.append((settings.company_abrev, settings.product_abrev))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_secret(self, name):
            assert name == 'insights-secret'
            return 'Endpoint=example'

    monkeypatch.setattr(bootstrap_module, 'KeyVaultClient', Resolver)
    config = load_configuration(process_root=tmp_path, environ={'ENVIRONMENT': 'dev'})
    assert config.require('APPLICATION_INSIGHTS_CONNECTION_STRING') == 'Endpoint=example'
    assert calls == [('ada', 'op')]
