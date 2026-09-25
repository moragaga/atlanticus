from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.source_projection import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.persistence.models import (
    AlarmConfigurationPersistenceSettings,
    AlarmConfigurationProjectionProvider,
    AlarmConfigurationSourceProvider,
)
from ada_command_center.web.alarms.projection.cosmos import (
    CosmosAlarmConfigurationProjectionStore,
    CosmosAlarmConfigurationProjectionStoreSettings,
)
from ada_command_center.web.alarms.projection.local import (
    LocalAlarmConfigurationProjectionStore,
    LocalAlarmConfigurationProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.store import SourceStore


@dataclass(frozen=True, slots=True)
class AlarmConfigurationPersistenceComposition:
    settings: AlarmConfigurationPersistenceSettings
    source: SourceStore
    projection: ProjectionStore[AlarmConfigurationSnapshot]
    projection_service: SourceProjectionService[AlarmConfigurationSnapshot]


def compose_alarm_configuration_persistence(
    *,
    settings: AlarmConfigurationPersistenceSettings,
    storage_client: StorageClient | None = None,
    cosmos_client: CosmosClient | None = None,
) -> AlarmConfigurationPersistenceComposition:
    if not isinstance(settings, AlarmConfigurationPersistenceSettings):
        raise TypeError('settings must be AlarmConfigurationPersistenceSettings')
    source = _compose_source(settings=settings, storage_client=storage_client)
    projection = _compose_projection(settings=settings, cosmos_client=cosmos_client)
    return AlarmConfigurationPersistenceComposition(
        settings=settings,
        source=source,
        projection=projection,
        projection_service=create_alarm_configuration_projection_service(
            source=source,
            projection=projection,
        ),
    )


def _compose_source(
    *,
    settings: AlarmConfigurationPersistenceSettings,
    storage_client: StorageClient | None,
) -> SourceStore:
    if settings.source_provider is AlarmConfigurationSourceProvider.LOCAL:
        if settings.local_source_root is None:
            raise RuntimeError('Local Alarm Configuration Source root is missing')
        return LocalSourceStore(LocalSourceSettings(root=settings.local_source_root))
    if storage_client is None:
        raise ValueError('Blob Alarm Configuration Source requires storage_client')
    if not isinstance(storage_client, StorageClient):
        raise TypeError('storage_client must be StorageClient')
    if settings.blob_container_name is None:
        raise RuntimeError('Blob Alarm Configuration Source container is missing')
    return BlobSourceStore(
        BlobSourceSettings(
            container_name=settings.blob_container_name,
            root_prefix=settings.blob_root_prefix,
        ),
        storage=storage_client,
    )


def _compose_projection(
    *,
    settings: AlarmConfigurationPersistenceSettings,
    cosmos_client: CosmosClient | None,
) -> ProjectionStore[AlarmConfigurationSnapshot]:
    if settings.projection_provider is AlarmConfigurationProjectionProvider.LOCAL:
        if settings.local_projection_root is None:
            raise RuntimeError('Local Alarm Configuration projection root is missing')
        return LocalAlarmConfigurationProjectionStore(
            LocalAlarmConfigurationProjectionStoreSettings(
                root=settings.local_projection_root,
            )
        )
    if cosmos_client is None:
        raise ValueError('Cosmos Alarm Configuration projection requires cosmos_client')
    if not isinstance(cosmos_client, CosmosClient):
        raise TypeError('cosmos_client must be CosmosClient')
    if settings.cosmos_container_name is None:
        raise RuntimeError('Cosmos Alarm Configuration projection container is missing')
    return CosmosAlarmConfigurationProjectionStore(
        client=cosmos_client,
        settings=CosmosAlarmConfigurationProjectionStoreSettings(
            container_name=settings.cosmos_container_name,
        ),
    )
