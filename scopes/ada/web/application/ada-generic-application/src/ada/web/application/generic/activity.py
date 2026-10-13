from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from azure.cosmos import CosmosClient as AzureCosmosClient

from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.web.users.activity import CosmosUserActivityRepository


@contextmanager
def open_durable_activity_repository(
    *,
    settings: CosmosSettings,
    container_name: str,
) -> Iterator[CosmosUserActivityRepository]:
    client = AzureCosmosClient(
        settings.endpoint,
        credential=settings.key,
        connection_timeout=settings.connection_timeout_seconds,
        timeout=settings.request_timeout_seconds,
        connection_mode='Gateway',
        retry_write=0,
    )
    try:
        container = client.get_database_client(settings.database_name).get_container_client(
            container_name
        )
        yield CosmosUserActivityRepository(container)
    finally:
        client.close()
