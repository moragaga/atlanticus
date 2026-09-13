from __future__ import annotations


class StorageTopologyError(Exception):
    pass


class StorageTopologyConfigurationError(StorageTopologyError):
    pass


class StorageResourceDeclarationConflictError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Conflicting storage resource declarations for logical_id {logical_id!r}')


class StorageResourceOverrideConflictError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Conflicting storage resource overrides for logical_id {logical_id!r}')


class UnknownStorageResourceOverrideError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Unknown storage resource override for logical_id {logical_id!r}')


class ForbiddenStorageResourceOverrideError(StorageTopologyError):
    def __init__(self, *, logical_id: str, field_name: str) -> None:
        self.logical_id = logical_id
        self.field_name = field_name
        super().__init__(
            f'Storage resource {logical_id!r} does not allow overriding {field_name!r}'
        )


class MissingStorageConnectionBindingError(StorageTopologyError):
    def __init__(self, *, logical_id: str) -> None:
        self.logical_id = logical_id
        super().__init__(f'Storage resource {logical_id!r} requires a connection binding')


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
