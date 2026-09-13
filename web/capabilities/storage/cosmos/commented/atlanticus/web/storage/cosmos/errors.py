from __future__ import annotations


# Error base público del bridge. No absorbe ni reemplaza errores propios de Connectivity Cosmos.
class CosmosStorageBridgeError(Exception):
    pass


# Errores detectables por composición o traducción antes de realizar I/O.
class CosmosStorageBridgeConfigurationError(CosmosStorageBridgeError):
    pass


# Un recurso declarado como Cosmos debe transportar exactamente la topology Cosmos soportada.
class CosmosStorageTopologyMismatchError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, logical_id: str, topology_type: str) -> None:
        self.logical_id = logical_id
        self.topology_type = topology_type
        super().__init__(
            f'Cosmos storage resource {logical_id!r} requires CosmosContainerTopology, '
            f'got {topology_type}'
        )


# El resolver ya exige connection_ref; aquí verificamos que composición entregó su provisioner.
class MissingCosmosProvisionerError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, connection_ref: str) -> None:
        self.connection_ref = connection_ref
        super().__init__(f'No Cosmos provisioner is bound to connection_ref {connection_ref!r}')


# Evita aceptar objetos con una interfaz accidentalmente parecida al provisioner contractual.
class InvalidCosmosProvisionerError(CosmosStorageBridgeConfigurationError):
    def __init__(self, *, connection_ref: str) -> None:
        self.connection_ref = connection_ref
        super().__init__(
            f'Cosmos provisioner for connection_ref {connection_ref!r} must be CosmosProvisioner'
        )


# Esta defensa evita que un plan construido manualmente llegue a I/O con containers duplicados.
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
