from __future__ import annotations

from types import SimpleNamespace

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
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.configuration import WebEnvironment


def _settings(
    tmp_path, *, tool_provider='blob', cosmos_provider='cosmos', container='ada-tool-projection'
):
    values = {
        'ATLANTICUS_ENVIRONMENT': 'local',
        'ADA_APPLICATION_NAMESPACE': 'ada-site',
        'ADA_TOOL_NAMESPACE': 'plant',
        'ADA_TOOL_SOURCE_PROVIDER': tool_provider,
        'ADA_TOOL_PROJECTION_PROVIDER': cosmos_provider,
        'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path.absolute()),
        'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME': 'configuration',
        'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ADA_TOOL_PROJECTION_COSMOS_KEY': 'test-only',
        'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME': 'ada',
        'ADA_TOOL_PROJECTION_COSMOS_CONTAINER_NAME': container,
    }
    return AdaGenericSettings.from_mapping(values)


def test_durable_manager_reuses_tool_connections_and_namespaces(tmp_path):
    deployment = resolve_durable_manager_configuration(_settings(tmp_path))
    assert deployment.namespace.application_prefix == 'ada-site'
    assert deployment.namespace.tool_prefix == 'ada-site/plant'
    assert deployment.resources.application_source == deployment.resources.tool_source
    assert deployment.resources.tool_source == deployment.resources.users_registry
    assert deployment.resources.application_source.container_name == 'configuration'
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


@pytest.mark.parametrize(
    ('source', 'projection', 'container', 'expected'),
    [
        ('local', 'cosmos', 'ada-tool-projection', 'Tool Blob Source'),
        ('blob', 'local', 'ada-tool-projection', 'Tool Cosmos'),
        ('blob', 'cosmos', 'other-projection', 'canonical resource contract'),
    ],
)
def test_invalid_durable_bindings_fail_before_network(
    tmp_path, source, projection, container, expected
):
    with pytest.raises(ValueError, match=expected):
        resolve_durable_manager_configuration(
            _settings(
                tmp_path, tool_provider=source, cosmos_provider=projection, container=container
            )
        )


def test_kpi_consumption_cannot_silently_point_to_another_cosmos(tmp_path):
    settings = _settings(tmp_path)
    alternate = AdaGenericSettings.from_mapping(
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
            'ADA_TOOL_PROJECTION_COSMOS_CONTAINER_NAME': 'ada-tool-projection',
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


def test_startup_selection_contract(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ADA_MANAGER_PERSISTENCE_PROVIDER', 'durable')
    assert ManagerStartupOptions().provider == 'durable'
    monkeypatch.setenv('ADA_MANAGER_PERSISTENCE_PROVIDER', 'unknown')
    with pytest.raises(ValueError):
        ManagerStartupOptions()


def test_real_durable_composition_requires_no_network_during_startup(tmp_path):
    with open_durable_manager(_settings(tmp_path)) as runtime:
        assert runtime.stores.navigation_source is runtime.stores.profiles_source
        assert runtime.stores.navigation_source is runtime.stores.access_source
        assert runtime.stores.tools_source is runtime.stores.kpi_registry_source
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
    with open_durable_manager(_settings(tmp_path)) as runtime:
        assert len(constructed) == 2
        assert not any(client.closed for client in constructed)
        assert runtime.stores['namespace'].tool_prefix == 'ada-site/plant'
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


def test_preparation_validates_blob_and_all_cosmos_without_mutation(tmp_path, monkeypatch):
    events = []
    settings = _settings(tmp_path)
    with open_durable_manager(settings) as runtime:
        monkeypatch.setattr(
            type(runtime.connections.storage['ada-blob']),
            'health_check',
            lambda self, *, container_name: events.append(('blob', container_name)),
        )
        monkeypatch.setattr(
            manager_deployment,
            'CosmosProvisioner',
            lambda *, client: SimpleNamespace(
                client=client, ensure_database=lambda: events.append(('ensure-db',))
            ),
        )
        monkeypatch.setattr(
            manager_deployment,
            'validate_cosmos_storage_plan',
            lambda plan, *, provisioners: events.append(('validate', len(plan.resources))),
        )
        names = prepare_durable_manager_resources(
            runtime, action='validate', environment=WebEnvironment.LOCAL
        )
    assert len(names) == 6
    assert events == [('blob', 'configuration'), ('validate', 6)]


def test_local_ensure_does_not_run_in_production_or_without_blob(tmp_path, monkeypatch):
    events = []
    with open_durable_manager(_settings(tmp_path)) as runtime:
        with pytest.raises(ValueError, match='restricted to local'):
            prepare_durable_manager_resources(
                runtime, action='ensure-local', environment=WebEnvironment.PRODUCTION
            )
        monkeypatch.setattr(
            type(runtime.connections.storage['ada-blob']),
            'health_check',
            lambda self, *, container_name: events.append(('blob', container_name)),
        )
        monkeypatch.setattr(
            manager_deployment,
            'CosmosProvisioner',
            lambda *, client: SimpleNamespace(
                client=client, ensure_database=lambda: events.append(('ensure-db',))
            ),
        )
        monkeypatch.setattr(
            manager_deployment,
            'ensure_cosmos_storage_plan',
            lambda plan, *, provisioners: events.append(('ensure-containers', len(plan.resources))),
        )
        prepare_durable_manager_resources(
            runtime, action='ensure-local', environment=WebEnvironment.LOCAL
        )
    assert events == [('blob', 'configuration'), ('ensure-db',), ('ensure-containers', 6)]


def test_unsupported_action_rejected_before_provider_access(tmp_path):
    with open_durable_manager(_settings(tmp_path)) as runtime:
        with pytest.raises(ValueError, match='Unknown'):
            prepare_durable_manager_resources(
                runtime, action='repair', environment=WebEnvironment.LOCAL
            )


@pytest.mark.parametrize('mode', ('auto', 'disabled'))
def test_cli_preserves_default_local_and_explicit_disabled(tmp_path, monkeypatch, mode):
    import importlib

    entrypoint = importlib.import_module('ada.web.application.generic.__main__')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ADA_MANAGER_PERSISTENCE_PROVIDER', mode)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:jane-doe')
    monkeypatch.setattr(
        entrypoint, 'AdaGenericSettings', lambda: SimpleNamespace(environment=WebEnvironment.LOCAL)
    )
    monkeypatch.setattr(entrypoint, 'create_local_configuration_manager_stores', lambda: 'local')
    calls = []
    monkeypatch.setattr(
        entrypoint,
        'create_operational_application_runtime',
        lambda **kwargs: calls.append(kwargs) or 'runtime',
    )
    monkeypatch.setattr(entrypoint, 'run_web_application', lambda runtime: calls.append(runtime))
    entrypoint.main()
    assert calls[-1] == 'runtime'
    if mode == 'auto':
        assert calls[0]['manager_stores'] == 'local'
        assert calls[0]['identity_provider'].resolve(None).subject_id == 'local:jane-doe'
    else:
        assert calls[0] == {'settings': entrypoint.AdaGenericSettings()}


def test_cli_durable_keeps_open_clients_during_server(tmp_path, monkeypatch):
    import importlib
    from contextlib import contextmanager

    entrypoint = importlib.import_module('ada.web.application.generic.__main__')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ADA_MANAGER_PERSISTENCE_PROVIDER', 'durable')
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:john-doe')
    monkeypatch.setattr(
        entrypoint, 'AdaGenericSettings', lambda: SimpleNamespace(environment=WebEnvironment.LOCAL)
    )
    events = []

    @contextmanager
    def fake_manager(settings):
        events.append('opened')
        yield SimpleNamespace(stores='durable')
        events.append('closed')

    monkeypatch.setattr(entrypoint, 'open_durable_manager', fake_manager)
    monkeypatch.setattr(
        entrypoint,
        'create_operational_application_runtime',
        lambda **kwargs: events.append(kwargs) or 'runtime',
    )
    monkeypatch.setattr(
        entrypoint, 'run_web_application', lambda runtime: events.append(('served', runtime))
    )
    entrypoint.main()
    assert events[0] == 'opened'
    assert events[1]['manager_stores'] == 'durable'
    assert events[1]['identity_provider'].resolve(None).subject_id == 'local:john-doe'
    assert events[2] == ('served', 'runtime')
    assert events[3] == 'closed'


def test_production_cli_requires_external_identity_in_durable_mode(tmp_path, monkeypatch):
    import importlib

    from atlanticus.web.identity.errors import IdentityConfigurationError

    entrypoint = importlib.import_module('ada.web.application.generic.__main__')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ADA_MANAGER_PERSISTENCE_PROVIDER', 'durable')
    monkeypatch.setattr(
        entrypoint,
        'AdaGenericSettings',
        lambda: SimpleNamespace(environment=WebEnvironment.PRODUCTION),
    )
    with pytest.raises(IdentityConfigurationError, match='injected production identity'):
        entrypoint.main()
