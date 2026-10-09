from __future__ import annotations

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosAuthenticationError,
    CosmosClient,
    CosmosContainerInventoryLimitError,
    CosmosDatabaseNotFoundError,
    CosmosInventory,
    CosmosOperationError,
    CosmosSettings,
    CosmosThrottledError,
)


class CosmosHttpError(Exception):
    def __init__(self, code: int) -> None:
        self.status_code = code


class FakeDatabase:
    def __init__(self, items=(), *, read_error=None, list_error=None):
        self.items = items
        self.read_error = read_error
        self.list_error = list_error
        self.read_calls = 0
        self.list_calls = 0

    def read(self):
        self.read_calls += 1
        if self.read_error is not None:
            raise self.read_error
        return {'id': 'testdb'}

    def list_containers(self):
        self.list_calls += 1
        if self.list_error is not None:
            raise self.list_error
        return iter(self.items)


def client_with(database):
    client = CosmosClient(
        settings=CosmosSettings(
            endpoint='https://localhost:8081', key='example', database_name='testdb'
        )
    )
    client._database = database
    return client


def container(name, paths=('/id',), ttl=None):
    return {'id': name, 'partitionKey': {'paths': list(paths)}, 'defaultTtl': ttl}


def test_inventory_returns_sorted_physical_properties_without_writes():
    database = FakeDatabase([container('users', ('/tenant', '/id'), -1), container('access')])
    result = CosmosInventory(client=client_with(database)).list_containers()
    assert [item.name for item in result] == ['access', 'users']
    assert result[1].partition_key_paths == ('/tenant', '/id')
    assert result[1].default_ttl_seconds == -1
    assert result[0].default_ttl_seconds is None
    assert database.read_calls == 1
    assert database.list_calls == 1


def test_empty_database_is_distinct_from_missing_database():
    assert CosmosInventory(client=client_with(FakeDatabase())).list_containers() == ()
    database = FakeDatabase(read_error=CosmosHttpError(404))
    with pytest.raises(CosmosDatabaseNotFoundError):
        CosmosInventory(client=client_with(database)).list_containers()
    assert database.list_calls == 0


@pytest.mark.parametrize(
    'status,exception', [(401, CosmosAuthenticationError), (429, CosmosThrottledError)]
)
def test_sdk_statuses_are_sanitized(status, exception):
    database = FakeDatabase(list_error=CosmosHttpError(status))
    with pytest.raises(exception):
        CosmosInventory(client=client_with(database)).list_containers()


def test_inventory_does_not_silently_truncate():
    database = FakeDatabase([container('a'), container('b'), container('c')])
    with pytest.raises(CosmosContainerInventoryLimitError) as error:
        CosmosInventory(client=client_with(database)).list_containers(max_items=2)
    assert error.value.max_items == 2


@pytest.mark.parametrize('limit', [0, -1, True, '3'])
def test_invalid_limit_is_rejected_before_io(limit):
    database = FakeDatabase()
    with pytest.raises(ValueError):
        CosmosInventory(client=client_with(database)).list_containers(max_items=limit)
    assert database.read_calls == 0


def test_invalid_or_duplicate_container_metadata_fails_closed():
    for items in ([{'id': 'x'}], [container('duplicate'), container('duplicate')]):
        with pytest.raises(CosmosOperationError):
            CosmosInventory(client=client_with(FakeDatabase(items))).list_containers()


class FakeContainer:
    def __init__(self, *, name='records', error=None):
        self.name = name
        self.error = error

    def read(self):
        if self.error is not None:
            raise self.error
        return container(self.name, ('/tenant',), -1)


class FakeDatabaseWithContainer(FakeDatabase):
    def __init__(self, target):
        super().__init__()
        self.target = target

    def get_container_client(self, name):
        assert name == 'records'
        return self.target


def test_read_one_container_without_listing_database():
    database = FakeDatabaseWithContainer(FakeContainer())
    result = CosmosInventory(client=client_with(database)).read_container(container_name='records')
    assert result.partition_key_paths == ('/tenant',)
    assert result.default_ttl_seconds == -1
    assert database.read_calls == 1
    assert database.list_calls == 0


def test_read_container_rejects_missing_or_changed_identity():
    from atlanticus.connectivity.cosmos import CosmosContainerNotFoundError

    database = FakeDatabaseWithContainer(FakeContainer(error=CosmosHttpError(404)))
    with pytest.raises(CosmosContainerNotFoundError):
        CosmosInventory(client=client_with(database)).read_container(container_name='records')
    database = FakeDatabaseWithContainer(FakeContainer(name='changed'))
    with pytest.raises(CosmosOperationError, match='identity changed'):
        CosmosInventory(client=client_with(database)).read_container(container_name='records')
