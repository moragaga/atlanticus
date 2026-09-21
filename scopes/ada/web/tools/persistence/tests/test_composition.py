from pathlib import Path

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolSourceProvider,
    compose_tool_persistence,
)
from ada.web.tools.projection.cosmos import CosmosToolProjectionStore
from ada.web.tools.projection.local import LocalToolProjectionStore
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionStringCredential,
    StorageSettings,
)
from atlanticus.web.source.blob import BlobSourceStore
from atlanticus.web.source.local import LocalSourceStore


def _namespace(tool: str = 'operaciones_integradas') -> AdaStorageNamespace:
    return AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace=tool,
    )


def _storage_client() -> StorageClient:
    return StorageClient(
        settings=StorageSettings(
            credential=StorageConnectionStringCredential('UseDevelopmentStorage=true')
        )
    )


def _cosmos_client() -> CosmosClient:
    return CosmosClient(
        settings=CosmosSettings(
            endpoint='https://localhost:8081',
            key='development-key',
            database_name='configuration',
        )
    )


def test_local_local_composition_uses_tool_namespace_without_creating_data(
    tmp_path: Path,
) -> None:
    composition = compose_tool_persistence(
        settings=ToolPersistenceSettings(
            namespace=_namespace('mina'),
            source_provider=ToolSourceProvider.LOCAL,
            projection_provider=ToolProjectionProvider.LOCAL,
            local_base_root=tmp_path,
        )
    )

    assert isinstance(composition.source, LocalSourceStore)
    assert isinstance(composition.projection, LocalToolProjectionStore)
    assert not (tmp_path / 'conciencia_situacional' / 'mina').exists()


def test_blob_cosmos_composition_is_lazy_and_does_not_require_live_services() -> None:
    composition = compose_tool_persistence(
        settings=ToolPersistenceSettings(
            namespace=_namespace(),
            source_provider=ToolSourceProvider.BLOB,
            projection_provider=ToolProjectionProvider.COSMOS,
            blob_container_name='configuration',
            cosmos_container_name='ada-tool-projection',
        ),
        storage_client=_storage_client(),
        cosmos_client=_cosmos_client(),
    )

    assert isinstance(composition.source, BlobSourceStore)
    assert isinstance(composition.projection, CosmosToolProjectionStore)


def test_source_and_projection_providers_can_be_mixed(tmp_path: Path) -> None:
    blob_local = compose_tool_persistence(
        settings=ToolPersistenceSettings(
            namespace=_namespace('chancado'),
            source_provider=ToolSourceProvider.BLOB,
            projection_provider=ToolProjectionProvider.LOCAL,
            local_base_root=tmp_path,
            blob_container_name='configuration',
        ),
        storage_client=_storage_client(),
    )
    local_cosmos = compose_tool_persistence(
        settings=ToolPersistenceSettings(
            namespace=_namespace('flotacion_selectiva'),
            source_provider=ToolSourceProvider.LOCAL,
            projection_provider=ToolProjectionProvider.COSMOS,
            local_base_root=tmp_path,
            cosmos_container_name='ada-tool-projection',
        ),
        cosmos_client=_cosmos_client(),
    )

    assert isinstance(blob_local.source, BlobSourceStore)
    assert isinstance(blob_local.projection, LocalToolProjectionStore)
    assert isinstance(local_cosmos.source, LocalSourceStore)
    assert isinstance(local_cosmos.projection, CosmosToolProjectionStore)
