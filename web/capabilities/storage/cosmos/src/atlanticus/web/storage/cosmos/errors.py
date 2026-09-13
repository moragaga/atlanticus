from __future__ import annotations


class CosmosStorageBridgeError(Exception):
    pass


class CosmosStorageBridgeConfigurationError(CosmosStorageBridgeError):
    pass


class CosmosStorageTopologyMismatchError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, logical_id: str, topology_type: str) -> None:
        self.logical_id = logical_id
        self.topology_type = topology_type
        super().__init__(
            f'Cosmos storage resource {logical_id!r} requires CosmosContainerTopology, '
            f'got {topology_type}'
        )


class MissingCosmosProvisionerError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, connection_ref: str) -> None:
        self.connection_ref = connection_ref
        super().__init__(f'No Cosmos provisioner is bound to connection_ref {connection_ref!r}')


class InvalidCosmosProvisionerError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, connection_ref: str) -> None:
        self.connection_ref = connection_ref
        super().__init__(
            f'Cosmos provisioner for connection_ref {connection_ref!r} must be CosmosProvisioner'
        )


class CosmosContainerBindingConflictError(CosmosStorageBridgeConfigurationError):
    def __init__(
        self,
        *,
        connection_ref: str,
        container_name: str,
        logical_id: str,
        conflicting_logical_id: str,
    ) -> None:
        self.connection_ref = connection_ref
        self.container_name = container_name
        self.logical_id = logical_id
        self.conflicting_logical_id = conflicting_logical_id
        super().__init__(
            'Cosmos storage resources '
            f'{conflicting_logical_id!r} and {logical_id!r} resolve to container '
            f'{container_name!r} on connection_ref {connection_ref!r}'
        )
