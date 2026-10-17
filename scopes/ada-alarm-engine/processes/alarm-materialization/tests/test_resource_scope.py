from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.processes.alarm_materialization.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _composition(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-alarm-materialization-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'ada-alarm',
        'ADA_COMMAND_CENTER_COSMOS_KEY': 'local-key',
        'ALARM_MATERIALIZATION_POLL_SECONDS': '1',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    return build_composition(configuration=configuration)


def _exercise(tmp_path, monkeypatch, *, fail):
    composition = _composition(tmp_path)
    lease = (
        tmp_path
        / 'ada-alarm-materialization-local'
        / '.runtime'
        / 'leases'
        / 'alarm-materialization.json'
    )
    events = []
    original_close = composition.cosmos.close

    def close_cosmos():
        assert lease.exists()
        events.append('cosmos_close')
        original_close()

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise ValueError('Materialization failed')

    monkeypatch.setattr(composition.cosmos, 'close', close_cosmos)
    composition.job = SimpleNamespace(run_iteration=iteration)

    if fail:
        with pytest.raises(ValueError, match='Materialization failed'):
            composition.execute(argv=())
    else:
        result = composition.execute(argv=())
        assert result.stop_reason == 'run_once'
        assert result.iteration_count == 1

    assert events == ['iteration', 'cosmos_close']
    assert not lease.exists()


def test_cosmos_closes_under_lease_after_success(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=False)


def test_cosmos_closes_under_lease_after_iteration_failure(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=True)


def test_cosmos_close_failure_releases_lease(tmp_path, monkeypatch):
    composition = _composition(tmp_path)
    lease = (
        tmp_path
        / 'ada-alarm-materialization-local'
        / '.runtime'
        / 'leases'
        / 'alarm-materialization.json'
    )
    events = []
    original_close = composition.cosmos.close

    def failing_close():
        assert lease.exists()
        events.append('cosmos_close')
        original_close()
        raise RuntimeError('Cosmos close failed')

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    monkeypatch.setattr(composition.cosmos, 'close', failing_close)
    composition.job = SimpleNamespace(run_iteration=iteration)

    with pytest.raises(RuntimeError, match='Cosmos close failed'):
        composition.execute(argv=())

    assert events == ['iteration', 'cosmos_close']
    assert not lease.exists()
