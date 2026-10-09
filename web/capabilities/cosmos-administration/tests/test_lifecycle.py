from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerDefinitionMismatchError,
    CosmosContainerNotFoundError,
    CosmosDatabaseNotFoundError,
    CosmosSettings,
)
from atlanticus.web.cosmos_administration import (
    CosmosLifecycleConfigurationError,
    CosmosLifecycleService,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ResolvedStoragePlan,
    ResolvedStorageResource,
)


class FakeError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeContainer:
    def __init__(self, name: str, *, exists: bool = False, path: str = '/tenant', ttl=None):
        self.name = name
        self.exists = exists
        self.path = path
        self.ttl = ttl
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        if not self.exists:
            raise FakeError(404)
        return {
            'id': self.name,
            'partitionKey': {'paths': [self.path]},
            'defaultTtl': self.ttl,
        }


class FakeDatabase:
    def __init__(self, name: str):
        self.name = name
        self.exists = True
        self.containers = {}
        self.read_calls = 0
        self.create_calls = []

    def read(self):
        self.read_calls += 1
        if not self.exists:
            raise FakeError(404)
        return {'id': self.name}

    def get_container_client(self, name: str):
        return self.containers.setdefault(name, FakeContainer(name))

    def create_container(self, *, id, partition_key, default_ttl):
        self.create_calls.append((id, partition_key.path, default_ttl))
        container = self.get_container_client(id)
        if container.exists:
            raise FakeError(409)
        container.exists = True
        container.path = partition_key.path
        container.ttl = default_ttl
        return container


class FakeCosmos(CosmosClient):
    def __init__(self, name: str):
        self.settings = CosmosSettings(
            endpoint='https://localhost:8081', key='private', database_name=name
        )
        self.database = FakeDatabase(name)
        self.created_databases = []
        self._database = self.database
        self._containers = {}
        self._sdk = SimpleNamespace(
            PartitionKey=lambda *, path: SimpleNamespace(path=path),
            CosmosHttpResponseError=FakeError,
        )

    def _get_database(self):
        return self.database

    def _get_sdk(self):
        return self._sdk

    def _get_client(self):
        return self

    def create_database(self, name: str):
        self.created_databases.append(name)
        self.database.exists = True
        return self.database


def resource(logical_id: str, name: str, *, connection: str = 'primary', ttl=None):
    return ResolvedStorageResource(
        logical_id=logical_id,
        owner='example',
        provider='cosmos',
        connection_ref=connection,
        physical_name=name,
        topology=CosmosContainerTopology('/tenant', ttl),
    )


def compose(resources=None, connections=None):
    clients = connections if connections is not None else {'primary': FakeCosmos('database')}
    resolved = resources if resources is not None else (resource('runtime', 'runtime-users'),)
    service = CosmosLifecycleService(connections=clients, plan=ResolvedStoragePlan(tuple(resolved)))
    return service, clients


def test_managed_catalog_uses_resolved_plan_and_excludes_non_cosmos():
    blob = ResolvedStorageResource(
        logical_id='blob',
        owner='example',
        provider='blob',
        connection_ref='unbound-blob',
        physical_name='assets',
        topology=object(),
    )
    service, _ = compose(resources=(resource('z', 'z-physical'), blob, resource('a', 'a-physical')))
    managed = service.list_managed_containers()
    assert [(item.logical_id, item.spec.name) for item in managed] == [
        ('a', 'a-physical'),
        ('z', 'z-physical'),
    ]
    assert all(item.database_name == 'database' for item in managed)
    assert all(item.spec.partition_key_path == '/tenant' for item in managed)


def test_unknown_logical_id_cannot_be_prepared_or_validated():
    service, clients = compose()
    for operation in (service.prepare_container, service.validate_container):
        with pytest.raises(CosmosLifecycleConfigurationError, match='not approved'):
            operation(logical_id='outsider')
    assert clients['primary'].database.read_calls == 0
    assert clients['primary'].database.create_calls == []


@pytest.mark.parametrize('connections', [{}, {'primary': object()}, {' ': object()}])
def test_invalid_connections_fail_before_io(connections):
    with pytest.raises(CosmosLifecycleConfigurationError):
        compose(connections=connections)


def test_missing_connection_binding_is_rejected_before_any_mutation():
    with pytest.raises(CosmosLifecycleConfigurationError, match='not configured'):
        compose(resources=(resource('x', 'container-x', connection='missing'),))


@pytest.mark.parametrize(
    'resources',
    [
        (resource('dup', 'x'), resource('dup', 'y')),
        (resource('first', 'shared'), resource('second', 'shared')),
    ],
)
def test_duplicate_logical_or_physical_bindings_are_rejected(resources):
    with pytest.raises(CosmosLifecycleConfigurationError, match='duplicated'):
        compose(resources=resources)


def test_validate_existing_requires_no_writes():
    service, clients = compose()
    db = clients['primary'].database
    db.get_container_client('runtime-users').exists = True
    report = service.validate_container(logical_id='runtime')
    assert (report.action, report.status, report.database_created) == ('validate', 'READY', False)
    assert report.container.logical_id == 'runtime'
    assert db.create_calls == []
    assert clients['primary'].created_databases == []


def test_validate_missing_database_never_creates():
    service, clients = compose()
    clients['primary'].database.exists = False
    with pytest.raises(CosmosDatabaseNotFoundError):
        service.validate_container(logical_id='runtime')
    assert clients['primary'].created_databases == []


def test_validate_missing_container_never_creates():
    service, clients = compose()
    with pytest.raises(CosmosContainerNotFoundError):
        service.validate_container(logical_id='runtime')
    assert clients['primary'].database.create_calls == []


def test_prepare_missing_container_creates_once_and_verifies():
    service, clients = compose()
    first = service.prepare_container(logical_id='runtime')
    second = service.prepare_container(logical_id='runtime')
    db = clients['primary'].database
    assert first.status == 'CREATED'
    assert first.database_created is False
    assert second.status == 'READY'
    assert db.create_calls == [('runtime-users', '/tenant', None)]
    assert db.get_container_client('runtime-users').read_calls >= 3


def test_prepare_missing_database_creates_it_and_container():
    service, clients = compose()
    clients['primary'].database.exists = False
    result = service.prepare_container(logical_id='runtime')
    assert result.status == 'CREATED'
    assert result.database_created is True
    assert clients['primary'].created_databases == ['database']


def test_existing_incompatible_partition_or_ttl_never_recreates():
    for path, ttl in (('/other', None), ('/tenant', 100)):
        service, clients = compose()
        container = clients['primary'].database.get_container_client('runtime-users')
        container.exists = True
        container.path = path
        container.ttl = ttl
        with pytest.raises(CosmosContainerDefinitionMismatchError):
            service.prepare_container(logical_id='runtime')
        assert clients['primary'].database.create_calls == []


def test_prepare_is_isolated_to_named_connection():
    primary = FakeCosmos('db-primary')
    secondary = FakeCosmos('db-secondary')
    service, _ = compose(
        resources=(
            resource('one', 'first', connection='primary'),
            resource('two', 'second', connection='secondary'),
        ),
        connections={'primary': primary, 'secondary': secondary},
    )
    result = service.prepare_container(logical_id='two')
    assert result.container.connection_ref == 'secondary'
    assert secondary.database.create_calls == [('second', '/tenant', None)]
    assert primary.database.read_calls == 0
    assert primary.database.create_calls == []


def test_an_empty_approved_plan_does_not_allow_arbitrary_preparation():
    service, _ = compose(resources=())
    assert service.list_managed_containers() == ()
    with pytest.raises(CosmosLifecycleConfigurationError):
        service.prepare_container(logical_id='runtime')
