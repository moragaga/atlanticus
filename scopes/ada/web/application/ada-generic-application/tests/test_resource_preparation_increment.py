from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.generic import resource_preparation
from ada.web.application.generic.manager_deployment import (
    DurableManagerRuntime,
    prepare_durable_manager_resources,
    resolve_durable_manager_configuration,
)
from ada.web.application.generic.manager_persistence import ManagerPersistenceConnections
from ada.web.application.generic.resource_preparation import ResourcePreparationStatus as Status
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.configuration import WebEnvironment


def _configuration():
    settings = AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_APPLICATION_NAMESPACE': 'ada-site',
            'ADA_TOOL_NAMESPACE': 'plant',
            'ADA_TOOL_SOURCE_PROVIDER': 'blob',
            'ADA_TOOL_PROJECTION_PROVIDER': 'cosmos',
            'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
            'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_TOOL_PROJECTION_COSMOS_KEY': 'test-only',
            'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'ada',
        }
    )
    return resolve_durable_manager_configuration(settings)


def _deployment(
    monkeypatch, *, database_created=False, created=(), failures=(), database_failure=False
):
    events = []
    storage = SimpleNamespace(
        settings=SimpleNamespace(),
        health_check=lambda **kwargs: events.append(('blob-check', kwargs['container_name'])),
    )
    cosmos = SimpleNamespace(
        settings=SimpleNamespace(database_name='ada'),
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

    monkeypatch.setattr(resource_preparation, 'CosmosProvisioner', Provisioner)
    monkeypatch.setattr(
        resource_preparation,
        'ensure_local_blob_container',
        lambda settings, name: events.append(('blob-ensure', name)) or True,
    )
    config = _configuration()
    deployment = DurableManagerRuntime(
        stores=None,
        resources=config.resources,
        connections=ManagerPersistenceConnections(
            storage={'ada-blob': storage},
            cosmos={'ada-cosmos': cosmos},
        ),
    )
    return deployment, events


def _raise(error):
    raise error


def _cosmos(report):
    return [item for item in report.results if item.kind == 'cosmos-container']


def test_local_prepare_creates_missing_database_blob_and_each_container(monkeypatch):
    deployment, events = _deployment(
        monkeypatch,
        database_created=True,
        created={'users-support', 'users-runtime'},
    )
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.LOCAL,
    )
    assert report.status == 'COMPLETED'
    assert len(_cosmos(report)) == 6
    assert report.results[0].status is Status.CREATED
    assert report.results[1].status is Status.CREATED
    assert {x.physical_name for x in _cosmos(report) if x.status is Status.CREATED} == {
        'users-support',
        'users-runtime',
    }
    assert events[0] == ('blob-ensure', 'configuration')
    assert events[1] == ('database-ensure',)
    assert all(event[0] != 'blob-check' for event in events)


def test_production_prepares_only_cosmos_containers_and_never_touches_blob_or_database_creation(
    monkeypatch,
):
    deployment, events = _deployment(monkeypatch, created={'users-support'})
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'COMPLETED'
    assert report.results[0].status is Status.SKIPPED
    assert ('database-check',) in events
    assert ('container-ensure', 'users-support') in events
    assert not any(item[0].startswith('blob') or item[0] == 'database-ensure' for item in events)


def test_validate_is_read_only_in_both_environments(monkeypatch):
    for environment in (WebEnvironment.LOCAL, WebEnvironment.PRODUCTION):
        deployment, events = _deployment(monkeypatch)
        report = prepare_durable_manager_resources(
            deployment,
            action='validate',
            environment=environment,
        )
        assert report.status == 'COMPLETED'
        assert all(item.status is Status.READY for item in _cosmos(report))
        assert ('database-check',) in events
        assert not any(event[0].endswith('ensure') for event in events)
        if environment.is_local:
            assert ('blob-check', 'configuration') in events
        else:
            assert not any(event[0].startswith('blob') for event in events)


def test_container_failure_is_isolated_and_reported_without_leaking_exception_message(
    monkeypatch,
):
    deployment, events = _deployment(monkeypatch, failures={'users-runtime'})
    failures = []
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
        observe_failure=failures.append,
    )
    assert report.status == 'PARTIAL'
    assert len(failures) == 1
    assert failures[0].physical_name == 'users-runtime'
    assert failures[0].error_type == 'RuntimeError'
    assert 'provisioning-failure' not in str(report.to_dict())
    assert len(_cosmos(report)) == 6
    assert all(
        item.status is Status.READY
        for item in _cosmos(report)
        if item.physical_name != 'users-runtime'
    )
    assert events.index(('container-ensure', 'users-runtime')) < len(events) - 1


def test_database_failure_blocks_all_cosmos_containers_without_mutations(monkeypatch):
    deployment, events = _deployment(monkeypatch, database_failure=True)
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'FAILED'
    assert report.results[0].status is Status.SKIPPED
    assert report.results[1].status is Status.FAILED
    assert all(item.status is Status.BLOCKED for item in _cosmos(report))
    assert events == [('database-check',)]


def test_subsequent_invocation_rechecks_failed_resource(monkeypatch):
    deployment, events = _deployment(monkeypatch, failures={'users-runtime'})
    first = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert first.status == 'PARTIAL'
    deployment, second_events = _deployment(monkeypatch)
    second = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert second.status == 'COMPLETED'
    assert ('container-ensure', 'users-runtime') in second_events


def test_contract_rejects_unsupported_action_without_touching_resources(monkeypatch):
    deployment, events = _deployment(monkeypatch)
    with pytest.raises(ValueError, match='Unknown'):
        prepare_durable_manager_resources(
            deployment,
            action='ensure-local',
            environment=WebEnvironment.LOCAL,
        )
    assert events == []


def test_observer_failure_does_not_mask_preparation_result(monkeypatch):
    deployment, _ = _deployment(monkeypatch, failures={'users-runtime'})

    def broken_observer(_item):
        raise RuntimeError('observer-down')

    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
        observe_failure=broken_observer,
    )
    assert report.status == 'PARTIAL'


@pytest.mark.parametrize(
    ('existing', 'race', 'expected_created'),
    [
        (True, False, False),
        (False, False, True),
        (False, True, False),
    ],
)
def test_local_blob_creation_is_idempotent_and_rechecks_races(
    monkeypatch,
    existing,
    race,
    expected_created,
):
    import sys
    from types import ModuleType

    from atlanticus.connectivity.storage import StorageConnectionStringCredential, StorageSettings

    calls = []
    state = {'exists': existing}

    class ExistsError(Exception):
        pass

    class Client:
        @classmethod
        def from_connection_string(cls, credential):
            calls.append('client')
            assert credential == 'example-secret'
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_container_client(self, name):
            assert name == 'example-container'
            return self

        def exists(self):
            calls.append('exists')
            return state['exists']

        def create_container(self, name):
            calls.append('create')
            if race:
                state['exists'] = True
                raise ExistsError('concurrent create')
            state['exists'] = True

    for name in ('azure', 'azure.core', 'azure.storage'):
        obj = ModuleType(name)
        obj.__path__ = []
        monkeypatch.setitem(sys.modules, name, obj)
    error_module = ModuleType('azure.core.exceptions')
    error_module.ResourceExistsError = ExistsError
    blob_module = ModuleType('azure.storage.blob')
    blob_module.BlobServiceClient = Client
    monkeypatch.setitem(sys.modules, 'azure.core.exceptions', error_module)
    monkeypatch.setitem(sys.modules, 'azure.storage.blob', blob_module)

    settings = StorageSettings(credential=StorageConnectionStringCredential('example-secret'))
    created = resource_preparation.ensure_local_blob_container(settings, 'example-container')
    assert created is expected_created
    assert calls.count('create') == (not existing)
    assert calls.count('exists') == (2 if race else 1)


def test_production_never_attempts_blob_access_even_if_connection_missing(monkeypatch):
    deployment, events = _deployment(monkeypatch)
    deployment.connections.storage.clear()
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'COMPLETED'
    assert report.results[0].status is Status.SKIPPED
    assert not any(event[0].startswith('blob') for event in events)


def test_container_topology_mismatch_is_reported_without_repairing_it(monkeypatch):
    deployment, events = _deployment(monkeypatch, failures={'users-runtime'})

    class DefinitionMismatch(RuntimeError):
        pass

    monkeypatch.setattr(
        resource_preparation,
        'CosmosContainerDefinitionMismatchError',
        DefinitionMismatch,
    )
    provisioner = resource_preparation.CosmosProvisioner
    original = provisioner.ensure_containers

    def with_mismatch(self, specs):
        if specs[0].name == 'users-runtime':
            raise DefinitionMismatch('Incompatible partition key')
        return original(self, specs)

    monkeypatch.setattr(provisioner, 'ensure_containers', with_mismatch)
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'PARTIAL'
    incompatible = [item for item in report.results if item.status is Status.INCOMPATIBLE]
    assert len(incompatible) == 1
    assert incompatible[0].physical_name == 'users-runtime'
    assert incompatible[0].error_type == 'DefinitionMismatch'
    assert ('container-ensure', 'users-support') in events


def test_missing_local_blob_is_reported_without_blocking_independent_cosmos(monkeypatch):
    deployment, _ = _deployment(monkeypatch)

    class MissingBlob(RuntimeError):
        pass

    monkeypatch.setattr(resource_preparation, 'StorageContainerNotFoundError', MissingBlob)
    deployment.connections.storage['ada-blob'].health_check = lambda **_kwargs: _raise(
        MissingBlob('missing-blob')
    )
    report = prepare_durable_manager_resources(
        deployment,
        action='validate',
        environment=WebEnvironment.LOCAL,
    )
    assert report.status == 'PARTIAL'
    assert report.results[0].status is Status.MISSING
    assert all(item.status is Status.READY for item in _cosmos(report))


def test_missing_productive_database_is_not_created(monkeypatch):
    deployment, events = _deployment(monkeypatch)

    class MissingDatabase(RuntimeError):
        pass

    monkeypatch.setattr(resource_preparation, 'CosmosDatabaseNotFoundError', MissingDatabase)
    deployment.connections.cosmos['ada-cosmos'].health_check = lambda: _raise(
        MissingDatabase('missing-db')
    )
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    assert report.status == 'FAILED'
    assert report.results[1].status is Status.MISSING
    assert all(item.status is Status.BLOCKED for item in _cosmos(report))
    assert events == []


def test_report_is_json_serializable_and_never_includes_exception_messages(monkeypatch):
    import json

    deployment, _ = _deployment(monkeypatch, failures={'users-runtime'})
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )
    payload = json.dumps(report.to_dict(), sort_keys=True)
    assert 'users-runtime' in payload
    assert 'RuntimeError' in payload
    assert 'provisioning-failure' not in payload


def test_local_database_failure_does_not_hide_blob_result(monkeypatch):
    deployment, events = _deployment(monkeypatch, database_failure=True)
    report = prepare_durable_manager_resources(
        deployment,
        action='prepare',
        environment=WebEnvironment.LOCAL,
    )
    assert report.status == 'PARTIAL'
    assert report.results[0].status is Status.CREATED
    assert report.results[1].status is Status.FAILED
    assert all(item.status is Status.BLOCKED for item in _cosmos(report))
    assert events == [('blob-ensure', 'configuration'), ('database-ensure',)]


def test_local_blob_preparer_supports_sas_credentials(monkeypatch):
    import sys
    from types import ModuleType

    from atlanticus.connectivity.storage import StorageSasCredential, StorageSettings

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

        def create_container(self, _name):
            pytest.fail('Existing Blob container must not be recreated')

    for name in ('azure', 'azure.core', 'azure.storage'):
        obj = ModuleType(name)
        obj.__path__ = []
        monkeypatch.setitem(sys.modules, name, obj)
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
    created = resource_preparation.ensure_local_blob_container(settings, 'example-container')
    assert created is False
    assert calls == [('https://storage.example.com', 'test-sas')]
