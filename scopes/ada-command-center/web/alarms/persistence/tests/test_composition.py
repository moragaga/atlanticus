from pathlib import Path

import pytest

from ada_command_center.web.alarms.persistence import (
    AlarmConfigurationPersistenceSettings,
    AlarmConfigurationProjectionProvider,
    AlarmConfigurationSourceProvider,
    compose_alarm_configuration_persistence,
)
from ada_command_center.web.alarms.projection.cosmos import (
    CosmosAlarmConfigurationProjectionStore,
)
from ada_command_center.web.alarms.projection.local import (
    LocalAlarmConfigurationProjectionStore,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionStringCredential,
    StorageSettings,
)
from atlanticus.web.source.blob import BlobSourceStore
from atlanticus.web.source.local import LocalSourceStore


def _storage() -> StorageClient:
    return StorageClient(
        settings=StorageSettings(
            credential=StorageConnectionStringCredential('UseDevelopmentStorage=true')
        )
    )


def _cosmos() -> CosmosClient:
    return CosmosClient(
        settings=CosmosSettings(
            endpoint='https://localhost:8081',
            key='development-key',
            database_name='configuration',
        )
    )


def test_local_local_composition_does_not_create_data(tmp_path: Path) -> None:
    source_root = tmp_path / 'source'
    projection_root = tmp_path / 'projection'
    composition = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.LOCAL,
            projection_provider=AlarmConfigurationProjectionProvider.LOCAL,
            local_source_root=source_root,
            local_projection_root=projection_root,
        )
    )
    assert isinstance(composition.source, LocalSourceStore)
    assert isinstance(composition.projection, LocalAlarmConfigurationProjectionStore)
    assert composition.projection_service is not None
    assert not source_root.exists()
    assert not projection_root.exists()


def test_blob_cosmos_composition_does_not_require_network() -> None:
    composition = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.BLOB,
            projection_provider=AlarmConfigurationProjectionProvider.COSMOS,
            blob_container_name='configuration',
            cosmos_container_name='ada-command-center-alarm-configuration-projection',
        ),
        storage_client=_storage(),
        cosmos_client=_cosmos(),
    )
    assert isinstance(composition.source, BlobSourceStore)
    assert isinstance(composition.projection, CosmosAlarmConfigurationProjectionStore)


def test_provider_pairs_are_independent(tmp_path: Path) -> None:
    blob_local = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.BLOB,
            projection_provider=AlarmConfigurationProjectionProvider.LOCAL,
            local_projection_root=tmp_path / 'projection',
            blob_container_name='configuration',
        ),
        storage_client=_storage(),
    )
    local_cosmos = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.LOCAL,
            projection_provider=AlarmConfigurationProjectionProvider.COSMOS,
            local_source_root=tmp_path / 'source',
            cosmos_container_name='ada-command-center-alarm-configuration-projection',
        ),
        cosmos_client=_cosmos(),
    )
    assert isinstance(blob_local.projection, LocalAlarmConfigurationProjectionStore)
    assert isinstance(local_cosmos.source, LocalSourceStore)


def test_composition_requires_clients_for_remote_providers() -> None:
    with pytest.raises(ValueError, match='storage_client'):
        compose_alarm_configuration_persistence(
            settings=AlarmConfigurationPersistenceSettings(
                source_provider=AlarmConfigurationSourceProvider.BLOB,
                projection_provider=AlarmConfigurationProjectionProvider.LOCAL,
                local_projection_root=Path('/tmp/projection'),
                blob_container_name='configuration',
            )
        )
