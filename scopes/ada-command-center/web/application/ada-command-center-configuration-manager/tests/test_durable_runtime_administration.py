from ada_command_center.web.application.configuration_manager import (
    build_configuration_manager_surface,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
)
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.manager import ManagerPrincipal


class StorageStub(StorageClient):
    def __init__(self, *, settings):
        self.settings = settings

    def close(self):
        pass


class CosmosStub(CosmosClient):
    def __init__(self, *, settings):
        self.settings = settings

    def close(self):
        pass


def test_durable_runtime_mounts_administration_with_command_center_topology(
    tmp_path, monkeypatch
) -> None:
    from ada_command_center.web.application.configuration_manager import durable_runtime

    monkeypatch.setattr(durable_runtime, 'StorageClient', StorageStub)
    monkeypatch.setattr(durable_runtime, 'CosmosClient', CosmosStub)
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'durable',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
            'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'http://cosmos-emulator:8081',
            'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command_center',
            'ADA_COMMAND_CENTER_COSMOS_KEY': 'test-only-key',
        },
    )
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )

    with open_durable_configuration_manager(
        reader=reader,
        principal_provider=lambda: principal,
    ) as dependencies:
        definition = build_configuration_manager_surface(dependencies)

    assert dependencies.administration is not None
    assert tuple(group.key for group in definition.groups) == ('administration', 'configuration')
    assert tuple(module.key for module in definition.modules) == (
        'profiles',
        'navigation',
        'alarm-configuration',
    )
    assert tuple(entry.key for entry in definition.entries) == ('users', 'tool-catalog')
    assert dependencies.source_name == 'Blob Storage'
    assert dependencies.projection_name == 'Cosmos DB'
