from __future__ import annotations


# Error base de la capability. Permite capturar cualquier fallo propio sin confundirlo con errores del provider.
class StorageTopologyError(Exception):
    pass


# Indica que el caller construyó un contrato o entrada con una forma inválida.
class StorageTopologyConfigurationError(StorageTopologyError):
    pass


# Dos capabilities declararon el mismo logical_id, pero no describen exactamente el mismo recurso.
class StorageResourceDeclarationConflictError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(
            f'Conflicting storage resource declarations for logical_id {logical_id!r}'
        )


# Una composición entregó más de un override incompatible para el mismo recurso lógico.
class StorageResourceOverrideConflictError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Conflicting storage resource overrides for logical_id {logical_id!r}')


# Un override referencia un logical_id que ninguna capability declaró.
class UnknownStorageResourceOverrideError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Unknown storage resource override for logical_id {logical_id!r}')


# La capability no autorizó que la composición cambie este campo de binding.
class ForbiddenStorageResourceOverrideError(StorageTopologyError):
    def __init__(self, *, logical_id: str, field_name: str) -> None:
        self.logical_id = logical_id
        self.field_name = field_name
        super().__init__(
            f'Storage resource {logical_id!r} does not allow overriding {field_name!r}'
        )


# El recurso no trae una conexión por defecto y la composición tampoco entregó una.
class MissingStorageConnectionBindingError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Storage resource {logical_id!r} requires a connection binding')


# Dos logical_id diferentes terminaron apuntando al mismo recurso físico dentro del mismo provider y conexión.
class StoragePhysicalResourceConflictError(StorageTopologyError):
    def __init__(
        self,
        *,
        logical_id: str,
        conflicting_logical_id: str,
        provider: str,
        connection_ref: str,
        physical_name: str,
    ) -> None:
        self.logical_id = logical_id
        self.conflicting_logical_id = conflicting_logical_id
        self.provider = provider
        self.connection_ref = connection_ref
        self.physical_name = physical_name
        super().__init__(
            'Storage resources '
            f'{conflicting_logical_id!r} and {logical_id!r} resolve to the same physical resource '
            f'({provider!r}, {connection_ref!r}, {physical_name!r})'
        )
