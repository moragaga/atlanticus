from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.processes.kpi_timeseries_delivery.composition import build_composition
from atlanticus.connectivity.cosmos import CosmosSettings

from .test_composition import _configuration


def _composition(tmp_path):
    return build_composition(
        configuration=_configuration(tmp_path),
        connections={
            'tool_a': CosmosSettings(
                endpoint='http://localhost:8081',
                database_name='tool-a',
                key='local-key',
                allow_insecure_http=True,
            ),
        },
    )


def _exercise(tmp_path, monkeypatch, *, fail):
    composition = _composition(tmp_path)
    lease = tmp_path / 'ada-kpi-timeseries-delivery-local' / '.runtime' / 'leases' / 'kpi-timeseries-delivery.json'
    events = []
    pool = composition.parallel_publisher
    client = composition.clients['tool_a']
    original_pool_close = pool.close
    original_client_close = client.close

    def close_pool():
        assert lease.exists()
        events.append('pool_close')
        original_pool_close()

    def close_client():
        assert lease.exists()
        events.append('client_close')
        original_client_close()

    monkeypatch.setattr(pool, 'close', close_pool)
    monkeypatch.setattr(client, 'close', close_client)

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise ValueError('Delivery iteration failed')

    composition.job = SimpleNamespace(run_iteration=iteration)
    if fail:
        with pytest.raises(ValueError, match='Delivery iteration failed'):
            composition.execute(argv=('--run-once',))
    else:
        assert composition.execute(argv=('--run-once',)).stop_reason == 'run_once'
    assert events == ['iteration', 'pool_close', 'client_close']
    assert not lease.exists()


def test_resources_close_under_lease_after_success(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=False)


def test_resources_close_under_lease_after_iteration_error(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=True)
