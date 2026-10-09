from __future__ import annotations

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosDatabaseNotFoundError,
    CosmosSettings,
)
from atlanticus.web.cosmos_administration import (
    CosmosAdministrationConfigurationError,
    CosmosAdministrationService,
)


class FakeDatabase:
    def __init__(self, items=(), *, missing=False):
        self.items = items
        self.missing = missing
        self.calls = 0

    def read(self):
        self.calls += 1
        if self.missing:
            error = RuntimeError('not found')
            error.status_code = 404
            raise error
        return {'id': 'db'}

    def list_containers(self):
        return iter(self.items)


def client_for(name, database):
    client = CosmosClient(
        settings=CosmosSettings(endpoint='https://localhost:8081', key='secret', database_name=name)
    )
    client._database = database
    return client


def test_named_connections_are_sorted_and_do_not_expose_secrets():
    qa = client_for('qa-db', FakeDatabase())
    prod = client_for('prod-db', FakeDatabase())
    service = CosmosAdministrationService(connections={'prod': prod, 'qa': qa})
    result = service.list_connections()
    assert [(item.connection_ref, item.database_name) for item in result] == [
        ('prod', 'prod-db'),
        ('qa', 'qa-db'),
    ]
    assert 'secret' not in str(result)


def test_inventory_uses_only_requested_connection_and_physical_containers():
    prod_db = FakeDatabase([{'id': 'custom', 'partitionKey': {'paths': ['/pk']}}])
    qa_db = FakeDatabase()
    service = CosmosAdministrationService(
        connections={'prod': client_for('prod-db', prod_db), 'qa': client_for('qa-db', qa_db)}
    )
    report = service.inventory(connection_ref='prod')
    assert report.database_name == 'prod-db'
    assert report.connection_ref == 'prod'
    assert [(item.name, item.partition_key_paths) for item in report.containers] == [
        ('custom', ('/pk',))
    ]
    assert prod_db.calls == 1
    assert qa_db.calls == 0


def test_unknown_connection_never_falls_back_to_default():
    db = FakeDatabase()
    service = CosmosAdministrationService(connections={'main': client_for('db', db)})
    with pytest.raises(CosmosAdministrationConfigurationError):
        service.inventory(connection_ref='missing')
    assert db.calls == 0


def test_missing_database_error_propagates_without_being_treated_as_empty():
    service = CosmosAdministrationService(
        connections={'main': client_for('db', FakeDatabase(missing=True))}
    )
    with pytest.raises(CosmosDatabaseNotFoundError):
        service.inventory(connection_ref='main')


@pytest.mark.parametrize('connections', [{}, {'bad': object()}, {'  ': object()}])
def test_invalid_composition_is_rejected(connections):
    with pytest.raises(CosmosAdministrationConfigurationError):
        CosmosAdministrationService(connections=connections)
