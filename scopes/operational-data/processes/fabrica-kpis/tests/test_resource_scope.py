from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.storage import StorageClient
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.fabrica_kpis.composition import build_composition


def _composition(tmp_path, *, disabled=False):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-fabrica-kpis-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'STORAGE_ACCOUNT_SAS_URL_FABRICA_KPIS': 'https://example.blob.core.windows.net/kpis?sv=1',
        'FABRICA_IDLE_SECONDS': '5',
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'true' if disabled else 'false',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    composition = build_composition(configuration=configuration)
    storage = StorageClient(settings=composition.settings.connection.settings)
    composition.producer.storages = {'kpis': storage}
    return composition, storage


def _lease(tmp_path):
    return (
        tmp_path
        / 'operational-data-fabrica-kpis-local'
        / '.runtime'
        / 'leases'
        / 'fabrica-kpis-materialization.json'
    )


def _exercise(tmp_path, monkeypatch, *, fail=False):
    composition, storage = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def open_storage():
        assert lease.exists()
        events.append('open')
        return storage

    def close_storage():
        assert lease.exists()
        events.append('close')

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise RuntimeError('Fabrica KPIs iteration failed')

    monkeypatch.setattr(storage, 'open', open_storage)
    monkeypatch.setattr(storage, 'close', close_storage)
    composition.producer.job = SimpleNamespace(run_iteration=iteration)

    if fail:
        with pytest.raises(RuntimeError, match='Fabrica KPIs iteration failed'):
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
    composition, storage = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def failing_open():
        assert lease.exists()
        events.append('open')
        raise RuntimeError('Storage open failed')

    monkeypatch.setattr(storage, 'open', failing_open)
    composition.producer.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    with pytest.raises(RuntimeError, match='Storage open failed'):
        composition.execute(argv=())

    assert events == ['open']
    assert not lease.exists()


def test_storage_close_failure_propagates_and_releases_lease(tmp_path, monkeypatch):
    composition, storage = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def open_storage():
        assert lease.exists()
        events.append('open')
        return storage

    def failing_close():
        assert lease.exists()
        events.append('close')
        raise RuntimeError('Storage close failed')

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    monkeypatch.setattr(storage, 'open', open_storage)
    monkeypatch.setattr(storage, 'close', failing_close)
    composition.producer.job = SimpleNamespace(run_iteration=iteration)

    with pytest.raises(RuntimeError, match='Storage close failed'):
        composition.execute(argv=())

    assert events == ['open', 'iteration', 'close']
    assert not lease.exists()


def test_partial_storage_open_failure_closes_earlier_storage(tmp_path, monkeypatch):
    composition, first = _composition(tmp_path)
    second = StorageClient(settings=composition.settings.connection.settings)
    composition.producer.storages = {'first': first, 'second': second}
    lease = _lease(tmp_path)
    events = []

    def first_open():
        assert lease.exists()
        events.append('open_first')
        return first

    def first_close():
        assert lease.exists()
        events.append('close_first')

    def second_open():
        assert lease.exists()
        events.append('open_second')
        raise RuntimeError('Second Storage open failed')

    monkeypatch.setattr(first, 'open', first_open)
    monkeypatch.setattr(first, 'close', first_close)
    monkeypatch.setattr(second, 'open', second_open)
    composition.producer.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    with pytest.raises(RuntimeError, match='Second Storage open failed'):
        composition.execute(argv=())

    assert events == ['open_first', 'open_second', 'close_first']
    assert not lease.exists()


def test_multiple_storage_clients_close_in_reverse_order(tmp_path, monkeypatch):
    composition, first = _composition(tmp_path)
    second = StorageClient(settings=composition.settings.connection.settings)
    composition.producer.storages = {'first': first, 'second': second}
    lease = _lease(tmp_path)
    events = []

    for key, storage in (('first', first), ('second', second)):
        def open_storage(storage=storage, key=key):
            assert lease.exists()
            events.append(f'open_{key}')
            return storage

        def close_storage(key=key):
            assert lease.exists()
            events.append(f'close_{key}')

        monkeypatch.setattr(storage, 'open', open_storage)
        monkeypatch.setattr(storage, 'close', close_storage)

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    composition.producer.job = SimpleNamespace(run_iteration=iteration)
    result = composition.execute(argv=())

    assert result.stop_reason == 'run_once'
    assert events == ['open_first', 'open_second', 'iteration', 'close_second', 'close_first']
    assert not lease.exists()


def test_disabled_job_does_not_open_storage(tmp_path, monkeypatch):
    composition, storage = _composition(tmp_path, disabled=True)
    events = []
    monkeypatch.setattr(storage, 'open', lambda: events.append('open'))
    composition.producer.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    result = composition.execute(argv=())

    assert result.stop_reason == 'execution_disabled'
    assert result.iteration_count == 0
    assert events == []
    assert not _lease(tmp_path).exists()
