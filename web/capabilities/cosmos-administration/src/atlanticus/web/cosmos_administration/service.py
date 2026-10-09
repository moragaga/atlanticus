from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.cosmos.inventory import CosmosContainerProperties, CosmosInventory


class CosmosAdministrationConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CosmosConnectionInfo:
    connection_ref: str
    database_name: str


@dataclass(frozen=True, slots=True)
class CosmosInventoryReport:
    connection_ref: str
    database_name: str
    containers: tuple[CosmosContainerProperties, ...]


class CosmosAdministrationService:
    def __init__(self, *, connections: Mapping[str, CosmosClient]) -> None:
        if not isinstance(connections, Mapping) or not connections:
            raise CosmosAdministrationConfigurationError('Named Cosmos connections are required')
        normalized: dict[str, CosmosClient] = {}
        for name, client in connections.items():
            if not isinstance(name, str) or not name or name != name.strip():
                raise CosmosAdministrationConfigurationError('Cosmos connection name is invalid')
            if not isinstance(client, CosmosClient):
                raise CosmosAdministrationConfigurationError(
                    'Cosmos connection must use CosmosClient'
                )
            normalized[name] = client
        self._connections = normalized

    def list_connections(self) -> tuple[CosmosConnectionInfo, ...]:
        return tuple(
            CosmosConnectionInfo(name, client.settings.database_name)
            for name, client in sorted(self._connections.items())
        )

    def inventory(self, *, connection_ref: str, max_items: int = 200) -> CosmosInventoryReport:
        if not isinstance(connection_ref, str) or connection_ref not in self._connections:
            raise CosmosAdministrationConfigurationError('Cosmos connection is not configured')
        client = self._connections[connection_ref]
        return CosmosInventoryReport(
            connection_ref=connection_ref,
            database_name=client.settings.database_name,
            containers=CosmosInventory(client=client).list_containers(max_items=max_items),
        )
