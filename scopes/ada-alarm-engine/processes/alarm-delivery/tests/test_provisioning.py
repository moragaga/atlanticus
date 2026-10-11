from __future__ import annotations

import pytest

from ada.processes.alarm_delivery import provisioning
from ada.processes.alarm_delivery.provisioning import prepare_cosmos_containers
from atlanticus.connectivity.cosmos import CosmosSettings


def _connections():
    return {
        key: CosmosSettings(
            endpoint='https://cosmos.example.com:443/',
            database_name=f'{key}-db',
            key='local-test-key',
        )
        for key in ('tool_a', 'tool_b')
    }


def test_off_does_not_open_cosmos_or_check_containers(monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('OFF must not inspect Cosmos')

    monkeypatch.setattr(provisioning, 'CosmosClient', forbidden)
    assert prepare_cosmos_containers(mode='OFF', connections=_connections()) == ()


def test_ensure_creates_missing_and_validates_existing_once_before_job(monkeypatch):
    calls = []
    existing = {'tool_b-db'}

    class FakeClient:
        def __init__(self, *, settings):
            self.settings = settings

        def __enter__(self):
            calls.append(('open', self.settings.database_name))
            return self

        def __exit__(self, *_):
            calls.append(('close', self.settings.database_name))

    class FakeProvisioner:
        def __init__(self, *, client):
            self.client = client

        def ensure_containers(self, specs):
            assert len(specs) == 1
            spec = specs[0]
            assert spec.name == 'alarm-live-projection'
            assert spec.partition_key_path == '/tool_key'
            assert spec.default_ttl_seconds is None
            database = self.client.settings.database_name
            calls.append(('ensure', database))
            return () if database in existing else (spec.name,)

    monkeypatch.setattr(provisioning, 'CosmosClient', FakeClient)
    monkeypatch.setattr(provisioning, 'CosmosProvisioner', FakeProvisioner)
    assert prepare_cosmos_containers(mode='ENSURE', connections=_connections()) == (
        'tool_a',
        'tool_b',
    )
    assert calls == [
        ('open', 'tool_a-db'),
        ('ensure', 'tool_a-db'),
        ('close', 'tool_a-db'),
        ('open', 'tool_b-db'),
        ('ensure', 'tool_b-db'),
        ('close', 'tool_b-db'),
    ]


def test_ensure_rejects_database_collision_before_any_network_io(monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('must detect collision before opening Cosmos')

    monkeypatch.setattr(provisioning, 'CosmosClient', forbidden)
    destination = _connections()['tool_a']
    with pytest.raises(ValueError, match='own Cosmos database'):
        prepare_cosmos_containers(
            mode='ENSURE', connections={'tool_a': destination, 'tool_b': destination}
        )


def test_ensure_propagates_missing_database_without_creating_it(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *, settings):
            calls.append('connect')

        def __enter__(self):
            return self

        def __exit__(self, *_):
            calls.append('close')

    class FakeProvisioner:
        def __init__(self, *, client):
            pass

        def ensure_containers(self, specs):
            calls.append('ensure_containers')
            raise RuntimeError('Cosmos database was not found')

        def ensure_database(self):
            raise AssertionError('ENSURE must not create databases')

    monkeypatch.setattr(provisioning, 'CosmosClient', FakeClient)
    monkeypatch.setattr(provisioning, 'CosmosProvisioner', FakeProvisioner)
    with pytest.raises(RuntimeError, match='database was not found'):
        prepare_cosmos_containers(mode='ENSURE', connections={'tool_a': _connections()['tool_a']})
    assert calls == ['connect', 'ensure_containers', 'close']


@pytest.mark.parametrize('mode', ['', 'VALIDATE', 'CREATE', 'ensure', 'Off', None, True])
def test_unapproved_provision_modes_fail_before_network(mode, monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError('must validate mode first')

    monkeypatch.setattr(provisioning, 'CosmosClient', forbidden)
    with pytest.raises(ValueError, match='OFF or ENSURE'):
        prepare_cosmos_containers(mode=mode, connections=_connections())


def test_ensure_rejects_empty_connections():
    with pytest.raises(ValueError, match='named Cosmos connections'):
        prepare_cosmos_containers(mode='ENSURE', connections={})


def test_delivery_settings_define_off_by_default_and_accept_only_two_modes():
    from ada.processes.alarm_delivery.settings import (
        AlarmDeliverySettings,
        configuration_specs,
    )

    specs = {spec.key: spec for spec in configuration_specs()}
    assert specs['ADA_COSMOS_PROVISION_MODE'].default == 'OFF'

    class FakeConfig:
        def __init__(self, mode):
            self.data = {
                'ALARM_MODELER_APPLICATION': 'modeler',
                'APPLICATION': 'delivery',
                'ALARM_DELIVERY_POLL_SECONDS': '5',
                'ALARM_DELIVERY_MAX_WORKERS': '2',
                'ADA_COSMOS_PROVISION_MODE': mode,
            }

        def require(self, name):
            return self.data[name]

    import ada.processes.alarm_delivery.settings as module

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(module, 'ResolvedConfiguration', FakeConfig)
        for value in ('OFF', 'ENSURE'):
            assert (
                AlarmDeliverySettings.from_configuration(FakeConfig(value)).cosmos_provision_mode
                == value
            )
        with pytest.raises(ValueError, match='OFF or ENSURE'):
            AlarmDeliverySettings.from_configuration(FakeConfig('VALIDATE'))
    finally:
        monkeypatch.undo()
