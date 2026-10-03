from __future__ import annotations

import pytest

from ada.web.application.generic import manager_deployment
from ada.web.application.generic.manager_deployment import (
    ManagerStartupOptions,
    open_durable_manager,
    prepare_durable_manager_resources,
    resolve_durable_manager_configuration,
)
from ada.web.application.generic.manager_persistence import (
    resolve_manager_cosmos_plan_for_connection,
)
from ada.web.application.generic.settings import AdaGenericSettings, AdaPersistenceMode
from atlanticus.web.configuration import WebEnvironment


def _settings(tmp_path, *, database='ada'):
    return AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_APPLICATION_NAMESPACE': 'ada-site',
            'ADA_TOOL_NAMESPACE': 'plant',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path.absolute()),
            'ADA_STORAGE_CONTAINER_NAME': 'configuration',
            'ADA_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_COSMOS_KEY': 'test-only',
            'ADA_COSMOS_DATABASE_NAME': database,
        }
    )


def test_durable_manager_reuses_shared_connections_and_namespaces(tmp_path):
    deployment = resolve_durable_manager_configuration(_settings(tmp_path))
    assert deployment.namespace.application_prefix == 'ada-site'
    assert deployment.namespace.scope_prefix == 'ada-site/plant'
    assert deployment.resources.tool_source == deployment.resources.users_registry
    assert deployment.resources.tool_source.container_name == 'configuration'
    assert deployment.cosmos_settings.database_name == 'ada'
    assert deployment.storage_settings.credential.connection_string == 'UseDevelopmentStorage=true'
    expected = {resource.physical_name for resource in deployment.resources.cosmos_plan.resources}
    assert expected == {
        'navigation-projection',
        'users-support',
        'users-runtime',
        'ada-tool-projection',
        'ada-kpi-registry-projection',
        'ada-kpi-definition-projection',
    }
    assert {resource.connection_ref for resource in deployment.resources.cosmos_plan.resources} == {
        'ada-cosmos'
    }


def test_local_persistence_cannot_open_durable_manager(tmp_path):
    settings = AdaGenericSettings.from_mapping(
        {
            'ADA_TOOL_NAMESPACE': 'plant',
            'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
        }
    )
    with pytest.raises(ValueError, match='durable ADA persistence'):
        resolve_durable_manager_configuration(settings)


def test_kpi_consumption_cannot_silently_point_to_another_cosmos(tmp_path):
    settings = _settings(tmp_path)
    alternate = AdaGenericSettings.from_mapping(
        {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_PERSISTENCE_MODE': 'durable',
            'ADA_APPLICATION_NAMESPACE': 'ada-site',
            'ADA_TOOL_NAMESPACE': 'plant',
            'ADA_STORAGE_CONTAINER_NAME': 'configuration',
            'ADA_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_COSMOS_KEY': 'test-only',
            'ADA_COSMOS_DATABASE_NAME': 'ada',
            'COSMOS_CONSUMPTION_ENDPOINT': 'http://localhost:8081',
            'COSMOS_CONSUMPTION_KEY': 'test-only',
            'COSMOS_CONSUMPTION_DATABASE_NAME': 'another',
        }
    )
    assert settings.kpi_delivery_cosmos_settings() is None
    with pytest.raises(ValueError, match='one Cosmos database'):
        resolve_durable_manager_configuration(alternate)


def test_cosmos_plan_derives_all_bindings_from_canonical_contracts():
    with pytest.raises(ValueError, match='connection reference'):
        resolve_manager_cosmos_plan_for_connection(' ')
    plan = resolve_manager_cosmos_plan_for_connection('ada-cosmos')
    assert len(plan.resources) == 6
    assert {resource.connection_ref for resource in plan.resources} == {'ada-cosmos'}
    assert {
        resource.physical_name for resource in plan.resources if 'navigation' in resource.logical_id
    } == {'navigation-projection'}


def test_startup_selection_reads_the_single_persistence_variable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ADA_PERSISTENCE_MODE', 'durable')
    assert ManagerStartupOptions().provider is AdaPersistenceMode.DURABLE
    monkeypatch.setenv('ADA_PERSISTENCE_MODE', 'local')
    assert ManagerStartupOptions().provider is AdaPersistenceMode.LOCAL
    monkeypatch.setenv('ADA_PERSISTENCE_MODE', 'unknown')
    with pytest.raises(ValueError):
        ManagerStartupOptions()


def test_real_durable_composition_requires_no_network_during_startup(tmp_path):
    with open_durable_manager(_settings(tmp_path)) as runtime:
        assert runtime.stores.navigation_source is runtime.stores.profiles_source
        assert runtime.stores.navigation_source is runtime.stores.access_source
        assert runtime.stores.navigation_source is runtime.stores.tools_source
        assert runtime.stores.navigation_source is runtime.stores.kpi_registry_source
        assert runtime.stores.navigation_source is runtime.stores.kpi_definitions_source
        assert runtime.stores.navigation_source is runtime.stores.operational_source
        assert runtime.stores.users_promoted is not None
        assert runtime.resources.cosmos_plan.resources


def test_open_manager_closes_both_clients_and_is_lazy(tmp_path, monkeypatch):
    constructed = []

    class FakeClient:
        def __init__(self, *, settings):
            self.settings = settings
            self.closed = False
            constructed.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(manager_deployment, 'StorageClient', FakeClient)
    monkeypatch.setattr(manager_deployment, 'CosmosClient', FakeClient)
    monkeypatch.setattr(
        manager_deployment, 'compose_durable_manager_stores', lambda **kwargs: kwargs
    )
    monkeypatch.setattr(
        manager_deployment,
        '_attach_users_recovery',
        lambda stores, *_arguments: stores,
    )
    with open_durable_manager(_settings(tmp_path)) as runtime:
        assert len(constructed) == 2
        assert not any(client.closed for client in constructed)
        assert runtime.stores['namespace'].scope_prefix == 'ada-site/plant'
    assert all(client.closed for client in constructed)


def test_failed_composition_closes_clients(tmp_path, monkeypatch):
    closed = []

    class FakeClient:
        def __init__(self, *, settings):
            del settings

        def close(self):
            closed.append(True)

    monkeypatch.setattr(manager_deployment, 'StorageClient', FakeClient)
    monkeypatch.setattr(manager_deployment, 'CosmosClient', FakeClient)

    def fail(**kwargs):
        del kwargs
        raise RuntimeError('failed before serving requests')

    monkeypatch.setattr(manager_deployment, 'compose_durable_manager_stores', fail)
    with pytest.raises(RuntimeError, match='failed before serving'):
        with open_durable_manager(_settings(tmp_path)):
            pass
    assert len(closed) == 2


def test_preparation_wrapper_adapts_ada_resources_to_shared_coordinator(tmp_path, monkeypatch):
    calls = []
    expected = object()

    def fake_prepare(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(manager_deployment, 'prepare_resources', fake_prepare)
    with open_durable_manager(_settings(tmp_path)) as runtime:
        actual = prepare_durable_manager_resources(
            runtime,
            action='prepare',
            environment=WebEnvironment.PRODUCTION,
        )
        assert actual is expected
        assert len(calls) == 1
        call = calls[0]
        assert [
            (item.logical_id, item.connection_ref, item.container_name)
            for item in call['resources'].blob_containers
        ] == [('ada-blob', 'ada-blob', 'configuration')]
        assert call['resources'].cosmos_plan is runtime.resources.cosmos_plan
        assert call['connections'].storage is runtime.connections.storage
        assert call['connections'].cosmos is runtime.connections.cosmos
        assert call['action'] == 'prepare'
        assert call['environment'] is WebEnvironment.PRODUCTION
        assert call['observe_failure'] is None


def test_unsupported_action_rejected_before_provider_access(tmp_path):
    with open_durable_manager(_settings(tmp_path)) as runtime:
        with pytest.raises(ValueError, match='Unknown'):
            prepare_durable_manager_resources(
                runtime, action='repair', environment=WebEnvironment.LOCAL
            )
