from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

import ada_command_center.processes.alarms_runtime.bootstrap as bootstrap


def _write_env(root: Path, *, volume: str) -> None:
    (root / '.env').write_text(
        '\n'.join(
            (
                'ENVIRONMENT=local',
                'APPLICATION=ada-command-center-alarms-runtime-local',
                f'VOLUMEN_PATH={volume}',
                'ALARM_CONFIGURATION_SOURCE_KEY=alarm-configuration',
                'PI_SOURCE=NOTPII',
                'PI_APPLICATION=notpii-local',
                'ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY=test.technical',
                'ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION=v1',
            )
        )
        + '\n',
        encoding='utf-8',
    )


def test_local_configuration_resolves_required_contracts_and_default_period(tmp_path: Path):
    _write_env(tmp_path, volume=str(tmp_path))
    resolved = bootstrap.load_configuration(process_root=tmp_path, environ={})
    assert resolved.require('ALARM_CONFIGURATION_SOURCE_KEY') == 'alarm-configuration'
    assert resolved.require('ALARM_RUNTIME_POLL_SECONDS') == '5'


def test_run_passes_identical_resolved_environment_to_process(monkeypatch, tmp_path: Path):
    _write_env(tmp_path, volume=str(tmp_path))
    received = {}

    def create(*, configuration):
        received['configuration'] = configuration

        def execute(*, argv, environ):
            received['argv'] = argv
            received['environ'] = environ
            return 'executed'

        return SimpleNamespace(execute=execute)

    monkeypatch.setattr(bootstrap, 'build_application', create)
    assert bootstrap.run(process_root=tmp_path, environ={}, argv=('--help',)) == 'executed'
    assert received['environ'] == received['configuration'].values
    assert received['argv'] == ('--help',)


def test_relative_volume_is_rejected_before_building_application(tmp_path: Path):
    _write_env(tmp_path, volume='relative-volume')
    with pytest.raises(bootstrap.AlarmRuntimeBootstrapError, match='VOLUMEN_PATH'):
        bootstrap.run(process_root=tmp_path, environ={})


def test_module_entrypoint_delegates_to_bootstrap(monkeypatch):
    called = []
    monkeypatch.setattr(bootstrap, 'main', lambda: called.append('executed'))
    runpy.run_module('ada_command_center.processes.alarms_runtime.__main__', run_name='__main__')
    assert called == ['executed']
