from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.operational_data.processes.meteodata.composition import build_composition
from atlanticus.operational_data.processes.meteodata.settings import configuration_specs


def _composition(tmp_path, *, disabled=False):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-meteodata-local',
        'VOLUMEN_PATH': str(tmp_path.resolve()),
        'METEODATA_BASE_URL': 'https://example.com/met/',
        'METEODATA_TOKEN': 'local-fake-token',
        'ATLANTICUS_JOB_EXECUTION_DISABLED': 'true' if disabled else 'false',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    config = ConfigurationBootstrap.from_process(
        specs=configuration_specs(),
        process_values=values,
    ).load(process_values=values)
    return build_composition(configuration=config)


def _lease(tmp_path):
    return (
        tmp_path
        / 'operational-data-meteodata-local'
        / '.runtime'
        / 'leases'
        / 'meteodata-materialization.json'
    )


def _exercise(tmp_path, monkeypatch, *, fail=False):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []
    original_open = composition.client.open
    original_close = composition.client.close

    def open_http():
        assert lease.exists()
        events.append('open')
        original_open()

    def close_http():
        assert lease.exists()
        events.append('close')
        original_close()

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise RuntimeError('Meteodata iteration failed')

    monkeypatch.setattr(composition.client, 'open', open_http)
    monkeypatch.setattr(composition.client, 'close', close_http)
    composition.job = SimpleNamespace(run_iteration=iteration)

    if fail:
        with pytest.raises(RuntimeError, match='Meteodata iteration failed'):
            composition.execute(argv=())
    else:
        result = composition.execute(argv=())
        assert result.stop_reason == 'run_once'
        assert result.iteration_count == 1

    assert events == ['open', 'iteration', 'close']
    assert not lease.exists()


def test_http_opens_before_iteration_and_closes_under_lease(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch)


def test_http_closes_under_lease_when_iteration_fails(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=True)


def test_http_open_failure_never_starts_iteration_and_releases_lease(tmp_path, monkeypatch):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []

    def failing_open():
        assert lease.exists()
        events.append('open')
        raise RuntimeError('HTTP open failed')

    monkeypatch.setattr(composition.client, 'open', failing_open)
    composition.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    with pytest.raises(RuntimeError, match='HTTP open failed'):
        composition.execute(argv=())

    assert events == ['open']
    assert not lease.exists()


def test_http_close_failure_is_reported_and_releases_lease(tmp_path, monkeypatch):
    composition = _composition(tmp_path)
    lease = _lease(tmp_path)
    events = []
    original_close = composition.client.close

    def failing_close():
        assert lease.exists()
        events.append('close')
        original_close()
        raise RuntimeError('HTTP close failed')

    def iteration(context):
        context.assert_lease_current()
        events.append('iteration')

    monkeypatch.setattr(composition.client, 'close', failing_close)
    composition.job = SimpleNamespace(run_iteration=iteration)

    with pytest.raises(RuntimeError, match='HTTP close failed'):
        composition.execute(argv=())

    assert events == ['iteration', 'close']
    assert not lease.exists()


def test_disabled_job_does_not_open_http(tmp_path, monkeypatch):
    composition = _composition(tmp_path, disabled=True)
    events = []
    monkeypatch.setattr(composition.client, 'open', lambda: events.append('open'))
    composition.job = SimpleNamespace(run_iteration=lambda context: events.append('iteration'))

    result = composition.execute(argv=())

    assert result.stop_reason == 'execution_disabled'
    assert result.iteration_count == 0
    assert events == []
    assert not _lease(tmp_path).exists()
