import pytest

from ada_command_center.web.alarms.projection.cosmos.storage import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.durable_runtime import (
    open_durable_configuration_manager,
    resolve_durable_configuration,
)
from atlanticus.connectivity.storage import StorageConnectionStringCredential
from atlanticus.web.navigation.projection.cosmos import NAVIGATION_PROJECTION_STORAGE_RESOURCE
from atlanticus.web.profiles.projection.cosmos import PROFILES_PROJECTION_STORAGE_RESOURCE
from atlanticus.web.users.storage import USERS_RUNTIME_STORAGE_RESOURCE


def _values():
    return {
        'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
        'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
        'ADA_COMMAND_CENTER_COSMOS_ENDPOINT': 'https://command-center.example.com',
        'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME': 'command_center',
        'ADA_COMMAND_CENTER_COSMOS_KEY': 'test-only-key',
    }


def test_storage_uses_only_shared_connection_string() -> None:
    setting = catalog_storage_settings(_values())
    assert isinstance(setting.credential, StorageConnectionStringCredential)
    with pytest.raises(ValueError, match='STORAGE_CONNECTION_STRING'):
        catalog_storage_settings({'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations'})


def test_root_and_resources_derive_from_existing_contracts() -> None:
    values = _values()
    values.update(
        {
            'ADA_COMMAND_CENTER_CATALOG_BLOB_NAME': 'must-not-be-used',
            'ADA_COMMAND_CENTER_ALARM_BLOB_CONTAINER': 'must-not-be-used',
            'ADA_COMMAND_CENTER_CATALOG_BLOB_CONTAINER': 'must-not-be-used',
        }
    )
    resolved = resolve_durable_configuration(values, local=False)
    assert resolved.storage_container_name == 'configurations'
    assert resolved.namespace.tool_prefix == 'conciencia_situacional/command-center'
    assert resolved.catalog_blob_name == (
        'conciencia_situacional/command-center/tool-catalog/current.json'
    )
    assert resolved.source_root_prefix == 'conciencia_situacional/command-center'
    assert resolved.users_registry_blob_name == (
        'conciencia_situacional/command-center/users/users.json.gz'
    )
    assert (
        resolved.alarm_projection_container_name
        == ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.default_physical_name
    )
    assert (
        resolved.profiles_projection_container_name
        == PROFILES_PROJECTION_STORAGE_RESOURCE.default_physical_name
    )
    assert (
        resolved.navigation_projection_container_name
        == NAVIGATION_PROJECTION_STORAGE_RESOURCE.default_physical_name
    )
    assert (
        resolved.users_runtime_container_name
        == USERS_RUNTIME_STORAGE_RESOURCE.default_physical_name
    )
    assert ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.topology.partition_key_path == (
        '/partition_key'
    )
    assert resolved.cosmos_settings.database_name == 'command_center'


def test_requires_only_one_container_and_own_cosmos_connection() -> None:
    for name in _values():
        with pytest.raises(ValueError):
            resolve_durable_configuration(
                {key: value for key, value in _values().items() if key != name},
                local=False,
            )


def test_production_requires_explicit_authenticated_host_binding() -> None:
    class Reader:
        environment = 'production'

        def own(self):
            raise AssertionError('Credentials must not be read before host authorization')

    with (
        pytest.raises(ValueError, match='authenticated host'),
        open_durable_configuration_manager(
            reader=Reader(),
            principal_provider=lambda: None,
        ),
    ):
        pass


def test_durable_rejects_local_provider_before_loading_credentials(tmp_path) -> None:
    from ada_command_center.web.application.configuration_manager.catalog_configuration import (
        ManagerConfigurationReader,
    )

    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
        },
    )
    with (
        pytest.raises(ValueError, match='durable provider'),
        open_durable_configuration_manager(
            reader=reader,
            principal_provider=lambda: None,
        ),
    ):
        pass
