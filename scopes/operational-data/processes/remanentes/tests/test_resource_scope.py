from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.remanentes.composition import build_composition


def _composition(tmp_path, *, disabled=False):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-remanentes-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'STORAGE_ACCOUNT_CONNECTION_STRING_REMANENTES': 'UseDevelopmentStorage=true',
        'STORAGE_ACCOUNT_CONTAINER_NAME_REMANENTES': 'dataproduct',
        'REMANENTES_SOURCE_TIMEZONE': 'America/Santiago',
        'REMANENTES_IDLE_SECONDS': '30',
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'true' if disabled else 'false',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    return build_composition(configuration=configuration)


def _lease(tmp_path):
    return (
        tmp_path
        / 'operational-data-remanentes-local'
        / '.runtime'
        / 'leases'
        / 'remanentes-materialization.json'
    )


def _exercise(tmp_path, monkeypatch, *, fail=False):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def open_storage():
        assert lease.exists()
        events.append('open')
        return composition.producer.storage

    def close_storage():
        assert lease.exists()
        events.append('close')

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise RuntimeError('Remanentes iteration failed')

    monkeypatch.setattr(composition.producer.storage, 'open', open_storage)
    monkeypatch.setattr(composition.producer.storage, 'close', close_storage)
    composition.producer.job = SimpleNamespace(run_iteration=iteration)

    if fail:
        with pytest.raises(RuntimeError, match='Remanentes iteration failed'):
            composition.execute(argv=())
    else:
        result = composition.execute(argv=())
        assert result.stop_reason == 'run_once'
        assert result.iteration_count == 1

    assert events == ['open', 'iteration', 'close']
    assert not lease.exists()


def test_storage_opens_before_iteration_and_closes_under_lease(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch)


def test_storage_closes_under_lease_when_iteration_fails(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=True)


def test_storage_open_failure_prevents_iteration_and_releases_lease(tmp_path, monkeypatch):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def failing_open():
        assert lease.exists()
        events.append('open')
        raise RuntimeError('Storage open failed')

    monkeypatch.setattr(composition.producer.storage, 'open', failing_open)
    composition.producer.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    with pytest.raises(RuntimeError, match='Storage open failed'):
        composition.execute(argv=())

    assert events == ['open']
    assert not lease.exists()


def test_storage_close_failure_propagates_and_releases_lease(tmp_path, monkeypatch):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def open_storage():
        assert lease.exists()
        events.append('open')
        return composition.producer.storage

    def failing_close():
        assert lease.exists()
        events.append('close')
        raise RuntimeError('Storage close failed')

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    monkeypatch.setattr(composition.producer.storage, 'open', open_storage)
    monkeypatch.setattr(composition.producer.storage, 'close', failing_close)
    composition.producer.job = SimpleNamespace(run_iteration=iteration)

    with pytest.raises(RuntimeError, match='Storage close failed'):
        composition.execute(argv=())

    assert events == ['open', 'iteration', 'close']
    assert not lease.exists()


def test_disabled_job_does_not_open_storage(tmp_path, monkeypatch):
    composition = _composition(tmp_path, disabled=True)
    events = []
    monkeypatch.setattr(composition.producer.storage, 'open', lambda: events.append('open'))
    composition.producer.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    result = composition.execute(argv=())

    assert result.stop_reason == 'execution_disabled'
    assert result.iteration_count == 0
    assert events == []
    assert not _lease(tmp_path).exists()
