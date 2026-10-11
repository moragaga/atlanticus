from __future__ import annotations

from collections.abc import Mapping

from ada.processes.alarm_delivery.transport import LIVE_CONTAINER, LIVE_PARTITION_KEY
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerSpec,
    CosmosProvisioner,
    CosmosSettings,
)


def prepare_cosmos_containers(
    *,
    mode: str,
    connections: Mapping[str, CosmosSettings],
) -> tuple[str, ...]:
    if mode not in ('OFF', 'ENSURE'):
        raise ValueError('Cosmos provision mode must be OFF or ENSURE')
    if mode == 'OFF':
        return ()
    if not isinstance(connections, Mapping) or not connections:
        raise ValueError('ENSURE requires named Cosmos connections')
    spec = CosmosContainerSpec(
        name=LIVE_CONTAINER,
        partition_key_path=LIVE_PARTITION_KEY,
        default_ttl_seconds=None,
    )
    seen: set[tuple[str, str]] = set()
    destinations = sorted(connections.items())
    for tool_key, settings in destinations:
        if not isinstance(tool_key, str) or not tool_key:
            raise ValueError('Cosmos provision requires valid Tool keys')
        if not isinstance(settings, CosmosSettings):
            raise TypeError('Cosmos provision requires CosmosSettings destinations')
        destination = (settings.endpoint, settings.database_name)
        if destination in seen:
            raise ValueError('Each Tool must have its own Cosmos database')
        seen.add(destination)
    prepared: list[str] = []
    for tool_key, settings in destinations:
        with CosmosClient(settings=settings) as client:
            CosmosProvisioner(client=client).ensure_containers((spec,))
        prepared.append(tool_key)
    return tuple(prepared)
