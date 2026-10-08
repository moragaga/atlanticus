from types import SimpleNamespace

from ada_command_center.web.application.configuration_manager import deployment
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    CommandCenterDurableRuntime,
    resolve_durable_configuration,
)
from atlanticus.web.configuration import WebEnvironment


def _configuration():
    return resolve_durable_configuration(
        {
            'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
            'ADA_TOOL_NAMESPACE': 'command-center',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'command-center',
            'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'http://localhost:8081',
            'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command-center',
            'ADA_COMMAND_CENTER_COSMOS_KEY': 'test-only',
        },
        local=True,
    )


def test_command_center_adapts_only_resource_data_to_shared_coordinator(monkeypatch) -> None:
    observed = {}
    expected = object()

    def fake_prepare(**kwargs):
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(deployment, 'prepare_resources', fake_prepare)
    storage = SimpleNamespace()
    cosmos = SimpleNamespace()
    runtime = CommandCenterDurableRuntime(
        configuration=_configuration(),
        storage=storage,
        cosmos=cosmos,
    )

    result = deployment.prepare_durable_resources(
        runtime,
        action='prepare',
        environment=WebEnvironment.PRODUCTION,
    )

    assert result is expected
    resources = observed['resources']
    assert [
        (item.logical_id, item.connection_ref, item.container_name)
        for item in resources.blob_containers
    ] == [('command-center-storage', 'command-center-storage', 'command-center')]
    assert resources.cosmos_plan is runtime.configuration.cosmos_plan
    assert observed['connections'].storage == {'command-center-storage': storage}
    assert list(observed['connections'].cosmos.values()) == [cosmos]
    assert observed['action'] == 'prepare'
    assert observed['environment'] is WebEnvironment.PRODUCTION
    assert observed['observe_failure'] is None


def test_command_center_plan_contains_only_its_four_contractual_containers() -> None:
    configuration = _configuration()
    assert {
        (resource.physical_name, resource.topology.partition_key_path)
        for resource in configuration.cosmos_plan.resources
    } == {
        ('alarm-configuration', '/partition_key'),
        ('profiles-projection', '/partition_key'),
        ('navigation-projection', '/partition_key'),
        ('users-runtime', '/id'),
    }
