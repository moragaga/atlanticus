from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scheduler/scheduler.py'
SPEC = importlib.util.spec_from_file_location('atlanticus_alarm_scheduler_mount_test', MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scheduler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scheduler
SPEC.loader.exec_module(scheduler)


def _schedule(root):
    return scheduler.ProcessSchedule(
        name='alarms-delivery',
        image='test-alarms-delivery',
        env_file=root / 'processes/alarms-delivery/.env',
        config_file=root / 'processes/alarms-delivery/config.json',
        cpus=0.5,
        memory='1g',
        replica_timeout=610,
        replica_retry_limit=0,
        cron_expression='*/10 * * * *',
        parallelism=1,
    )


def test_scheduler_mounts_optional_connections_from_host_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    config = workspace / 'processes/alarms-delivery/config'
    config.mkdir(parents=True)
    (config / 'connections.detail.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(scheduler, 'WORKSPACE_ROOT', workspace)
    monkeypatch.setenv('HOSTNAME', 'scheduler-container')
    host_root = tmp_path / 'distribution'
    mounts = [{'Destination': str(workspace), 'Type': 'bind', 'Source': str(host_root)}]
    monkeypatch.setattr(
        scheduler, '_docker', lambda args: SimpleNamespace(stdout=json.dumps(mounts))
    )
    result = scheduler._config_mount(_schedule(workspace))
    assert result == [
        '--mount',
        'type=bind,source='
        + str(host_root / 'processes/alarms-delivery/config')
        + ',target=/app/process/config,readonly',
    ]


def test_scheduler_does_not_require_an_extra_mount_for_other_processes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(scheduler, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.setattr(
        scheduler,
        '_docker',
        lambda _: (_ for _ in ()).throw(AssertionError('Unexpected Docker call')),
    )
    assert scheduler._config_mount(_schedule(tmp_path)) == []


def test_scheduler_rejects_non_bind_workspace_mount(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    config = workspace / 'processes/alarms-delivery/config'
    config.mkdir(parents=True)
    (config / 'connections.detail.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(scheduler, 'WORKSPACE_ROOT', workspace)
    monkeypatch.setenv('HOSTNAME', 'scheduler-container')
    mounts = [{'Destination': str(workspace), 'Type': 'volume', 'Source': 'named'}]
    monkeypatch.setattr(
        scheduler, '_docker', lambda _: SimpleNamespace(stdout=json.dumps(mounts))
    )
    with pytest.raises(scheduler.SchedulerError, match='bind mount'):
        scheduler._config_mount(_schedule(workspace))
