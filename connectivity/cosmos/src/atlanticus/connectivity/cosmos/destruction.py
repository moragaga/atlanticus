from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atlanticus.connectivity.cosmos.client import CosmosClient
from atlanticus.connectivity.cosmos.errors import (
    CosmosContainerNotFoundError,
    CosmosOperationError,
    CosmosProvisioningError,
)
from atlanticus.observability import ErrorInfo, runtime_guard


def _safe_parameters(_: tuple[Any, ...], values: Mapping[str, Any]) -> Mapping[str, Any]:
    return {'container_name': values['container_name']}


def _safe_error(error: BaseException) -> ErrorInfo:
    return ErrorInfo(error_type=type(error).__name__, message='Cosmos container deletion failed')


class CosmosContainerDeletion:
    def __init__(self, *, client: CosmosClient) -> None:
        if not isinstance(client, CosmosClient):
            raise CosmosProvisioningError('Cosmos container deletion requires CosmosClient')
        self._client = client

    @runtime_guard(
        operation='cosmos.container.delete',
        component='atlanticus.connectivity.cosmos',
        parameter_mapper=_safe_parameters,
        error_mapper=_safe_error,
    )
    def delete_container(self, *, container_name: str, expected_etag: str) -> None:
        if (
            not isinstance(container_name, str)
            or not container_name
            or container_name != container_name.strip()
            or any(char in container_name for char in '/\\#?\t\r\n\x00')
            or len(container_name) > 255
        ):
            raise CosmosProvisioningError('Cosmos container name is invalid')
        if (
            not isinstance(expected_etag, str)
            or not expected_etag.strip()
            or expected_etag == '*'
            or any(ord(char) < 32 for char in expected_etag)
        ):
            raise CosmosProvisioningError('Cosmos container ETag is invalid')
        database = self._client._get_database()
        try:
            database.delete_container(
                container_name,
                etag=expected_etag,
                match_condition=self._client._get_sdk().MatchConditions.IfNotModified,
            )
        except Exception as error:
            self._client._raise_sdk_error(
                error,
                not_found_error=CosmosContainerNotFoundError,
                not_found_message='Cosmos container was not found',
                operation_message='Could not delete Cosmos container',
            )
            raise CosmosOperationError('Could not delete Cosmos container') from None
        self._client._containers.pop(container_name, None)
