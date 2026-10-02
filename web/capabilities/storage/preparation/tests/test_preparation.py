from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

import atlanticus.web.storage.preparation.core as preparation
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.storage.preparation import (
    BlobContainerResource,
    ResourcePreparationConnections,
    ResourcePreparationResources,
    ResourcePreparationStatus as Status,
    prepare_resources,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ResolvedStoragePlan,
    ResolvedStorageResource,
)


def _resources() -> ResourcePreparationResources:
    return ResourcePreparationResources(
        blob_containers=(BlobContainerResource('blob', 'storage', 'configuration'),),
        cosmos_plan=ResolvedStoragePlan(
            resources=(
                ResolvedStorageResource(
                    logical_id='alpha.projection',
                    owner='tests',
                    provider='cosmos',
                    connection_ref='cosmos',
                    physical_name='alpha-projection',
                    topology=CosmosContainerTopology('/partition_key'),
                ),
                ResolvedStorageResource(
                    logical_id='users.runtime',
                    owner='tests',
                    provider='cosmos',
                    connection_ref='cosmos',
                    physical_name='users-runtime',
                    topology=CosmosContainerTopology('/id'),
                ),
            )
        ),
    )


def _connections(
    monkeypatch,
    *,
    database_created=False,
    created=(),
    failures=(),
    database_failure=False,
):
    events = []
    storage = SimpleNamespace(
        settings=SimpleNamespace(),
        health_check=lambda **kwargs: events.append(('blob-check', kwargs['container_name'])),
    )
    cosmos = SimpleNamespace(
        settings=SimpleNamespace(database_name='database'),
        health_check=lambda: (
            events.append(('database-check',))
            or (_raise(RuntimeError('no-database')) if database_failure else True)
        ),
    )

    class Provisioner:
        def __init__(self, *, client):
            assert client is cosmos

        def ensure_database(self):
            events.append(('database-ensure',))
            if database_failure:
                raise RuntimeError('no-database')
            return database_created

        def ensure_containers(self, specs):
            assert len(specs) == 1
            name = specs[0].name
            events.append(('container-ensure', name))
            if name in failures:
                raise RuntimeError('provisioning-failure')
            return (name,) if name in created else ()

        def validate_containers(self, specs):
            assert len(specs) == 1
            name = specs[0].name
            events.append(('container-check', name))
            if name in failures:
                raise RuntimeError('missing-container')

    monkeypatch.setattr(preparation, 'CosmosProvisioner', Provisioner)
    monkeypatch.setattr(
        preparation,
        'ensure_local_blob_container',
        lambda settings, name: events.append(('blob-ensure', name)) or True,
    )
    return (
        ResourcePreparationConnections(
            storage={'storage': storage},
            cosmos={'cosmos': cosmos},
        ),
        events,
    )


def _raise(error):
    raise error


def _containers(report):
    return [item for item in report.results if item.kind == 'cosmos-container']


def test_local_prepare_preserves_ada_creation_semantics(monkeypatch) -> None:
    connections, events = _connections(
        monkeypatch,
        database_created=True,
        created={'users-runtime'},
    )
    report = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.LOCAL,
    )
    assert report.status == 'COMPLETED'
    assert report.results[0].status is Status.CREATED
    assert report.results[1].status is Status.CREATED
    assert {
        item.physical_name for item in _containers(report) if item.status is Status.CREATED
    } == {'users-runtime'}
    assert events[:2] == [('blob-ensure', 'configuration'), ('database-ensure',)]


def test_production_prepare_skips_blob_validates_database_and_ensures_containers(
    monkeypatch,
) -> None:
    connections, events = _connections(monkeypatch, created={'users-runtime'})
    report = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'COMPLETED'
    assert report.results[0].status is Status.SKIPPED
    assert ('database-check',) in events
    assert ('container-ensure', 'users-runtime') in events
    assert not any(event[0].startswith('blob') or event[0] == 'database-ensure' for event in events)


def test_validate_is_read_only_in_local_and_production(monkeypatch) -> None:
    for environment in (WebEnvironment.LOCAL, WebEnvironment.PRODUCTION):
        connections, events = _connections(monkeypatch)
        report = prepare_resources(
            resources=_resources(),
            connections=connections,
            action='validate',
            environment=environment,
        )
        assert report.status == 'COMPLETED'
        assert all(item.status is Status.READY for item in _containers(report))
        assert ('database-check',) in events
        assert not any(event[0].endswith('ensure') for event in events)
        if environment.is_local:
            assert ('blob-check', 'configuration') in events
        else:
            assert not any(event[0].startswith('blob') for event in events)


def test_container_failure_is_isolated_and_reported_without_exception_message(monkeypatch) -> None:
    connections, events = _connections(monkeypatch, failures={'users-runtime'})
    failures = []
    report = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
        observe_failure=failures.append,
    )
    assert report.status == 'PARTIAL'
    assert len(failures) == 1
    assert failures[0].physical_name == 'users-runtime'
    assert failures[0].error_type == 'RuntimeError'
    assert 'provisioning-failure' not in json.dumps(report.to_dict(), sort_keys=True)
    assert ('container-ensure', 'alpha-projection') in events


def test_database_failure_blocks_only_dependent_cosmos_resources(monkeypatch) -> None:
    connections, events = _connections(monkeypatch, database_failure=True)
    report = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'FAILED'
    assert report.results[0].status is Status.SKIPPED
    assert report.results[1].status is Status.FAILED
    assert all(item.status is Status.BLOCKED for item in _containers(report))
    assert events == [('database-check',)]


def test_contract_rejects_duplicate_blob_binding_and_unknown_action(monkeypatch) -> None:
    plan = _resources().cosmos_plan
    with pytest.raises(ValueError, match='repeat'):
        ResourcePreparationResources(
            blob_containers=(
                BlobContainerResource('one', 'storage', 'configuration'),
                BlobContainerResource('two', 'storage', 'configuration'),
            ),
            cosmos_plan=plan,
        )
    connections, events = _connections(monkeypatch)
    with pytest.raises(ValueError, match='Unknown'):
        prepare_resources(
            resources=_resources(),
            connections=connections,
            action='repair',
            environment=WebEnvironment.LOCAL,
        )
    assert events == []


def test_observer_failure_never_masks_resource_result(monkeypatch) -> None:
    connections, _ = _connections(monkeypatch, failures={'users-runtime'})

    def broken_observer(_item):
        raise RuntimeError('observer-down')

    report = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
        observe_failure=broken_observer,
    )
    assert report.status == 'PARTIAL'


@pytest.mark.parametrize(
    ('existing', 'race', 'expected_created'),
    [(True, False, False), (False, False, True), (False, True, False)],
)
def test_local_blob_creation_is_idempotent_and_rechecks_races(
    monkeypatch,
    existing,
    race,
    expected_created,
) -> None:
    calls = []
    state = {'exists': existing}

    class ExistsError(Exception):
        pass

    class Client:
        @classmethod
        def from_connection_string(cls, credential):
            calls.append(('client', credential))
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_container_client(self, name):
            assert name == 'example-container'
            return self

        def exists(self):
            calls.append(('exists',))
            return state['exists']

        def create_container(self, name):
            calls.append(('create', name))
            if race:
                state['exists'] = True
                raise ExistsError('concurrent create')
            state['exists'] = True

    for name in ('azure', 'azure.core', 'azure.storage'):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    errors = ModuleType('azure.core.exceptions')
    errors.ResourceExistsError = ExistsError
    blob = ModuleType('azure.storage.blob')
    blob.BlobServiceClient = Client
    monkeypatch.setitem(sys.modules, 'azure.core.exceptions', errors)
    monkeypatch.setitem(sys.modules, 'azure.storage.blob', blob)

    settings = StorageSettings(credential=StorageConnectionStringCredential('example-secret'))
    assert (
        preparation.ensure_local_blob_container(settings, 'example-container') is expected_created
    )
    assert sum(call[0] == 'create' for call in calls) == (not existing)
    assert sum(call[0] == 'exists' for call in calls) == (2 if race else 1)


def test_local_blob_creation_supports_sas_credentials(monkeypatch) -> None:
    calls = []

    class Client:
        def __init__(self, *, account_url, credential):
            calls.append((account_url, credential))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_container_client(self, name):
            assert name == 'example-container'
            return self

        def exists(self):
            return True

    for name in ('azure', 'azure.core', 'azure.storage'):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    errors = ModuleType('azure.core.exceptions')
    errors.ResourceExistsError = type('ResourceExistsError', (Exception,), {})
    blob = ModuleType('azure.storage.blob')
    blob.BlobServiceClient = Client
    monkeypatch.setitem(sys.modules, 'azure.core.exceptions', errors)
    monkeypatch.setitem(sys.modules, 'azure.storage.blob', blob)

    settings = StorageSettings(
        credential=StorageSasCredential(
            account_url='https://storage.example.com',
            sas_token='test-sas',
        )
    )
    assert preparation.ensure_local_blob_container(settings, 'example-container') is False
    assert calls == [('https://storage.example.com', 'test-sas')]


def test_known_missing_and_incompatible_errors_keep_stable_statuses(monkeypatch) -> None:
    class MissingBlob(RuntimeError):
        pass

    class DefinitionMismatch(RuntimeError):
        pass

    monkeypatch.setattr(preparation, 'StorageContainerNotFoundError', MissingBlob)
    monkeypatch.setattr(preparation, 'CosmosContainerDefinitionMismatchError', DefinitionMismatch)
    connections, _ = _connections(monkeypatch)
    connections.storage['storage'].health_check = lambda **_kwargs: _raise(MissingBlob('missing'))

    original = preparation.CosmosProvisioner.ensure_containers

    def with_mismatch(self, specs):
        if specs[0].name == 'users-runtime':
            raise DefinitionMismatch('incompatible')
        return original(self, specs)

    monkeypatch.setattr(preparation.CosmosProvisioner, 'ensure_containers', with_mismatch)
    validate = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='validate',
        environment=WebEnvironment.LOCAL,
    )
    assert validate.results[0].status is Status.MISSING

    prepare = prepare_resources(
        resources=_resources(),
        connections=connections,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    incompatible = [item for item in prepare.results if item.status is Status.INCOMPATIBLE]
    assert [item.physical_name for item in incompatible] == ['users-runtime']
