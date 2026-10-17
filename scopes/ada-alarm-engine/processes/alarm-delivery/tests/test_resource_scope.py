from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.processes.alarm_delivery.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment


def _composition(tmp_path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-alarm-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'ALARM_MODELER_APPLICATION': 'ada-alarm-modeler-local',
        'ALARM_DELIVERY_POLL_SECONDS': '5',
        'ALARM_DELIVERY_MAX_WORKERS': '2',
        'ADA_COSMOS_PROVISION_MODE': 'OFF',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    return build_composition(
        configuration=configuration,
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
    lease = tmp_path / 'ada-alarm-delivery-local' / '.runtime' / 'leases' / 'alarm-delivery.json'
    events = []
    publisher = composition.job.publisher
    original_close = publisher.close

    def close_publisher():
        assert lease.exists()
        events.append('publisher_close')
        original_close()

    def recovery(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('recovery')

    def iteration(context):
        context.assert_lease_current()
        assert lease.exists()
        events.append('iteration')
        if fail:
            raise ValueError('Alarm publication failed')

    monkeypatch.setattr(publisher, 'close', close_publisher)
    composition.job = SimpleNamespace(
        publisher=publisher,
        recover=recovery,
        run_iteration=iteration,
    )
    if fail:
        with pytest.raises(ValueError, match='Alarm publication failed'):
            composition.execute(argv=('--run-once',))
    else:
        assert composition.execute(argv=('--run-once',)).stop_reason == 'run_once'
    assert events == ['recovery', 'iteration', 'publisher_close']
    assert not lease.exists()


def test_publisher_closes_under_lease_after_success(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=False)


def test_publisher_closes_under_lease_after_failure(tmp_path, monkeypatch):
    _exercise(tmp_path, monkeypatch, fail=True)
