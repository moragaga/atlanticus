# Compone Source y Projection para una Tool sin ejecutar health checks ni lecturas.
# Construir esta composición nunca debe requerir que Blob o Cosmos estén disponibles.

from __future__ import annotations

from dataclasses import dataclass

from ada.web.tools.configuration import (
    ToolConfiguration,
    create_tool_projection_service,
)
from ada.web.tools.persistence.models import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolSourceProvider,
)
from ada.web.tools.projection.cosmos import (
    CosmosToolProjectionStore,
    CosmosToolProjectionStoreSettings,
)
from ada.web.tools.projection.local import (
    LocalToolProjectionStore,
    LocalToolProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.store import SourceStore


@dataclass(frozen=True, slots=True)
class ToolPersistenceComposition:
    settings: ToolPersistenceSettings
    source: SourceStore
    projection: ProjectionStore[ToolConfiguration]
    projection_service: SourceProjectionService[ToolConfiguration]


def compose_tool_persistence(
    *,
    settings: ToolPersistenceSettings,
    storage_client: StorageClient | None = None,
    cosmos_client: CosmosClient | None = None,
) -> ToolPersistenceComposition:
    if not isinstance(settings, ToolPersistenceSettings):
        raise TypeError('settings must be ToolPersistenceSettings')

    # Los clientes ya están configurados, pero no se abren ni se consultan aquí.
    source = _compose_source(
        settings=settings,
        storage_client=storage_client,
    )
    projection = _compose_projection(
        settings=settings,
        cosmos_client=cosmos_client,
    )
    return ToolPersistenceComposition(
        settings=settings,
        source=source,
        projection=projection,
        projection_service=create_tool_projection_service(
            source=source,
            projection=projection,
        ),
    )


def _compose_source(
    *,
    settings: ToolPersistenceSettings,
    storage_client: StorageClient | None,
) -> SourceStore:
    if settings.source_provider is ToolSourceProvider.LOCAL:
        base_root = settings.local_base_root
        if base_root is None:
            raise RuntimeError('Local Source provider has no local base root')
        # SourceStore recibe el root de Tool y agrega internamente sources/<SourceKey>.
        return LocalSourceStore(
            LocalSourceSettings(
                root=settings.namespace.local_tool_root(base_root),
            )
        )

    if storage_client is None:
        raise ValueError('Blob Source provider requires storage_client')
    if not isinstance(storage_client, StorageClient):
        raise TypeError('storage_client must be StorageClient')
    container_name = settings.blob_container_name
    if container_name is None:
        raise RuntimeError('Blob Source provider has no container name')
    # BlobSourceStore recibe el prefix de Tool y agrega internamente sources/<SourceKey>.
    return BlobSourceStore(
        BlobSourceSettings(
            container_name=container_name,
            root_prefix=settings.namespace.tool_prefix,
        ),
        storage=storage_client,
    )


def _compose_projection(
    *,
    settings: ToolPersistenceSettings,
    cosmos_client: CosmosClient | None,
) -> ProjectionStore[ToolConfiguration]:
    if settings.projection_provider is ToolProjectionProvider.LOCAL:
        base_root = settings.local_base_root
        if base_root is None:
            raise RuntimeError('Local Projection provider has no local base root')
        return LocalToolProjectionStore(
            LocalToolProjectionStoreSettings.from_namespace(
                namespace=settings.namespace,
                base_root=base_root,
            )
        )

    if cosmos_client is None:
        raise ValueError('Cosmos Projection provider requires cosmos_client')
    if not isinstance(cosmos_client, CosmosClient):
        raise TypeError('cosmos_client must be CosmosClient')
    container_name = settings.cosmos_container_name
    if container_name is None:
        raise RuntimeError('Cosmos Projection provider has no container name')
    # El store usa application/tool como partition key; SourceKey permanece genérico.
    return CosmosToolProjectionStore(
        client=cosmos_client,
        settings=CosmosToolProjectionStoreSettings.from_namespace(
            container_name=container_name,
            namespace=settings.namespace,
        ),
    )
