from __future__ import annotations

import logging

from ada.web.application.generic.operational_tool import (
    create_runtime_from_tool_resolution,
    resolve_operational_tool_projection,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.tools.persistence import compose_tool_persistence
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.connectivity.storage import StorageClient, StorageError
from atlanticus.web.models import WebApplicationRuntime

_LOGGER = logging.getLogger(__name__)


# Éste es el composition root operacional: settings -> clients -> persistence -> resolution -> runtime.
def create_operational_application_runtime(
    *,
    settings: AdaGenericSettings | None = None,
) -> WebApplicationRuntime:
    if settings is not None and not isinstance(settings, AdaGenericSettings):
        raise TypeError('settings must be AdaGenericSettings')
    resolved_settings = settings or AdaGenericSettings()
    storage_client = _create_storage_client(resolved_settings)
    cosmos_client = _create_cosmos_client(resolved_settings)
    try:
        # La composición es lazy respecto de conectividad; la lectura ocurre en el resolver.
        persistence = compose_tool_persistence(
            settings=resolved_settings.tool_persistence_settings(),
            storage_client=storage_client,
            cosmos_client=cosmos_client,
        )
        resolution = resolve_operational_tool_projection(persistence)
    finally:
        # El bootstrap sólo necesita estos clientes para resolver Tool; no quedan como estado global.
        _close_client(storage_client, 'Storage')
        _close_client(cosmos_client, 'Cosmos')
    return create_runtime_from_tool_resolution(resolution)


def _create_storage_client(settings: AdaGenericSettings) -> StorageClient | None:
    storage_settings = settings.storage_settings()
    if storage_settings is None:
        return None
    return StorageClient(settings=storage_settings)


def _create_cosmos_client(settings: AdaGenericSettings) -> CosmosClient | None:
    cosmos_settings = settings.cosmos_settings()
    if cosmos_settings is None:
        return None
    return CosmosClient(settings=cosmos_settings)


# Un fallo al cerrar una dependencia ya degradada no debe derribar la Web que ya fue resuelta.
def _close_client(client: StorageClient | CosmosClient | None, provider_name: str) -> None:
    if client is None:
        return
    try:
        client.close()
    except (StorageError, CosmosError) as error:
        _LOGGER.warning('Could not close %s client: %s', provider_name, error)
