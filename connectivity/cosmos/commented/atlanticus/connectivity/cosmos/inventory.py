from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import islice
from typing import Any

from atlanticus.connectivity.cosmos.client import CosmosClient
from atlanticus.connectivity.cosmos.errors import (
    CosmosContainerNotFoundError,
    CosmosDatabaseNotFoundError,
    CosmosError,
    CosmosOperationError,
)
from atlanticus.observability import ErrorInfo, ResultSummary, runtime_guard

_COMPONENT = 'atlanticus.connectivity.cosmos'


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosContainerInventoryLimitError(CosmosOperationError):
    # Validación y errores controlados antes de realizar operaciones.
    def __init__(self, *, max_items: int) -> None:
        self.max_items = max_items
        super().__init__(f'Cosmos container inventory exceeds max_items={max_items}')


@dataclass(frozen=True, slots=True)
# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosContainerProperties:
    name: str
    partition_key_paths: tuple[str, ...]
    default_ttl_seconds: int | None
    etag: str | None = None

    # Validación y errores controlados antes de realizar operaciones.
    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or self.name != self.name.strip():
            raise CosmosOperationError('Cosmos container metadata has an invalid name')
        paths = self.partition_key_paths
        if (
            not isinstance(paths, tuple)
            or not paths
            or any(
                not isinstance(path, str) or not path.startswith('/') or path == '/'
                for path in paths
            )
        ):
            raise CosmosOperationError('Cosmos container metadata has invalid partition keys')
        ttl = self.default_ttl_seconds
        if ttl is not None and (
            not isinstance(ttl, int) or isinstance(ttl, bool) or (ttl != -1 and ttl <= 0)
        ):
            raise CosmosOperationError('Cosmos container metadata has an invalid TTL')
        if self.etag is not None and (
            not isinstance(self.etag, str)
            or not self.etag.strip()
            or self.etag == '*'
            or any(ord(char) < 32 for char in self.etag)
        ):
            raise CosmosOperationError('Cosmos container metadata has an invalid ETag')


def _inventory_error(error: BaseException) -> ErrorInfo:
    message = (
        str(error) if isinstance(error, CosmosError | TypeError) else 'Cosmos inventory failed'
    )
    return ErrorInfo(error_type=type(error).__name__, message=message)


def _inventory_result(value: Any) -> ResultSummary:
    if isinstance(value, tuple):
        return ResultSummary(metrics={'container_count': len(value)})
    return ResultSummary()


def _container_properties(value: object) -> CosmosContainerProperties:
    if not isinstance(value, Mapping):
        raise CosmosOperationError('Cosmos container metadata is invalid')
    partition_key = value.get('partitionKey')
    if not isinstance(partition_key, Mapping):
        raise CosmosOperationError('Cosmos container metadata has no partition key')
    paths = partition_key.get('paths')
    if not isinstance(paths, list | tuple):
        raise CosmosOperationError('Cosmos container metadata has invalid partition keys')
    ttl = value.get('defaultTtl')
    return CosmosContainerProperties(
        name=value.get('id'),
        partition_key_paths=tuple(paths),
        default_ttl_seconds=ttl,
        etag=value.get('_etag'),
    )


# Contrato pedagógico: responsabilidad aislada y reutilizable.
class CosmosInventory:
    # Validación y errores controlados antes de realizar operaciones.
    def __init__(self, *, client: CosmosClient) -> None:
        if not isinstance(client, CosmosClient):
            raise TypeError('Cosmos inventory requires CosmosClient')
        self._client = client

    @runtime_guard(
        operation='cosmos.container.inspect',
        component=_COMPONENT,
        error_mapper=_inventory_error,
        emit_started=False,
    )
    # Validación y errores controlados antes de realizar operaciones.
    def read_container(self, *, container_name: str) -> CosmosContainerProperties:
        self._client.health_check()
        container = self._client._get_container(container_name)
        try:
            raw = container.read()
        except Exception as error:
            self._client._raise_sdk_error(
                error,
                not_found_error=CosmosContainerNotFoundError,
                not_found_message='Cosmos container was not found',
                operation_message='Could not inspect Cosmos container',
            )
            raise CosmosOperationError('Could not inspect Cosmos container') from None
        result = _container_properties(raw)
        if result.name != container_name:
            raise CosmosOperationError('Cosmos container identity changed during inspection')
        return result

    @runtime_guard(
        operation='cosmos.containers.inventory',
        component=_COMPONENT,
        result_mapper=_inventory_result,
        error_mapper=_inventory_error,
        emit_started=False,
    )
    # Validación y errores controlados antes de realizar operaciones.
    def list_containers(self, *, max_items: int = 200) -> tuple[CosmosContainerProperties, ...]:
        if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items <= 0:
            raise ValueError('max_items must be a positive integer')
        if max_items > self._client.settings.max_query_items:
            raise ValueError('max_items exceeds the configured Cosmos query limit')
        database = self._client._get_database()
        try:
            database.read()
            raw = tuple(islice(database.list_containers(), max_items + 1))
        except Exception as error:
            self._client._raise_sdk_error(
                error,
                not_found_error=CosmosDatabaseNotFoundError,
                not_found_message='Cosmos database was not found',
                operation_message='Could not list Cosmos containers',
            )
            raise CosmosOperationError('Could not list Cosmos containers') from None
        if len(raw) > max_items:
            raise CosmosContainerInventoryLimitError(max_items=max_items)
        result = tuple(
            sorted((_container_properties(item) for item in raw), key=lambda item: item.name)
        )
        names = tuple(item.name for item in result)
        if len(names) != len(set(names)):
            raise CosmosOperationError('Cosmos container inventory has duplicate names')
        return result
