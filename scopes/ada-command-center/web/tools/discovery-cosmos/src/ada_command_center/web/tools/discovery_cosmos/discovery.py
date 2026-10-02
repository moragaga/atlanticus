from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.projection_record import TOOL_PROJECTION_DOCUMENT_TYPE
from ada.web.tools.projection.cosmos import (
    TOOL_PROJECTION_STORAGE_RESOURCE,
    CosmosToolProjectionStore,
    CosmosToolProjectionStoreSettings,
)
from ada_command_center.web.tools.catalog import (
    DEFAULT_TOOL_SOURCE_KEY,
    ToolCatalogError,
    ToolCatalogInput,
    ToolCatalogSnapshot,
)
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerNotFoundError,
    CosmosError,
    CosmosQueryParameter,
    CosmosResultLimitError,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId
from atlanticus.web.storage.namespace import StorageNamespace

_CONNECTION_NAME = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
_DISCOVERY_QUERY = (
    'SELECT c.id, c.partition_key FROM c '
    'WHERE c.document_type = @document_type AND c.source_key = @source_key'
)
_MAX_DOCUMENTS = 256


class ToolCatalogDiscoveryError(ToolCatalogError):
    pass


class ToolCatalogConnectionStatus(StrEnum):
    READY = 'READY'
    NO_CONTAINER = 'NO_CONTAINER'
    NO_TOOLS = 'NO_TOOLS'
    ERROR = 'ERROR'


class ToolCatalogDiscoveryIssue(StrEnum):
    QUERY_FAILED = 'QUERY_FAILED'
    LIMIT_EXCEEDED = 'LIMIT_EXCEEDED'
    INVALID_DOCUMENT = 'INVALID_DOCUMENT'
    INVALID_NAMESPACE = 'INVALID_NAMESPACE'
    DUPLICATE_NAMESPACE = 'DUPLICATE_NAMESPACE'
    MISSING_PROJECTION = 'MISSING_PROJECTION'
    INVALID_PROJECTION = 'INVALID_PROJECTION'
    MISSING_STRUCTURE = 'MISSING_STRUCTURE'


@dataclass(frozen=True, slots=True)
class DiscoveredTool:
    connection_name: str
    namespace_key: str
    tool_key: str
    display_name: str
    kind: str
    source_release_id: SourceReleaseId
    configuration: ToolConfiguration = field(repr=False, compare=False)
    projection_store: ProjectionStore[ToolConfiguration] = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ToolConnectionInspection:
    connection_name: str
    status: ToolCatalogConnectionStatus
    tools: tuple[DiscoveredTool, ...] = ()
    issue: ToolCatalogDiscoveryIssue | None = None


@dataclass(frozen=True, slots=True)
class ToolCatalogDiscoveryReport:
    connections: tuple[ToolConnectionInspection, ...]

    def consolidation_inputs(
        self, *, current: ToolCatalogSnapshot | None
    ) -> tuple[ToolCatalogInput, ...]:
        if any(item.status is ToolCatalogConnectionStatus.ERROR for item in self.connections):
            raise ToolCatalogDiscoveryError('Tool discovery contains blocking connection errors')
        tools = tuple(tool for connection in self.connections for tool in connection.tools)
        if not tools:
            raise ToolCatalogDiscoveryError('Tool discovery has no confirmed candidates')
        if current is not None and not isinstance(current, ToolCatalogSnapshot):
            raise TypeError('current must be a ToolCatalogSnapshot or None')
        if current is not None:
            missing = {entry.tool_key for entry in current.tools} - {
                entry.tool_key for entry in tools
            }
            if missing:
                raise ToolCatalogDiscoveryError(
                    'Tool discovery cannot silently remove previously confirmed tools'
                )
        owners: dict[str, str] = {}
        inputs = []
        for tool in tools:
            input_key = f'{tool.connection_name}:{tool.namespace_key}'
            if tool.tool_key in owners:
                raise ToolCatalogDiscoveryError(
                    f'Tool discovery contains duplicate tool_key: {tool.tool_key}'
                )
            owners[tool.tool_key] = input_key
            inputs.append(
                ToolCatalogInput(
                    input_key=input_key,
                    projection=_PinnedToolProjectionStore(tool),
                )
            )
        return tuple(inputs)


class ToolCatalogDiscovery:
    def __init__(
        self,
        *,
        connections: Mapping[str, CosmosClient],
        max_documents_per_connection: int = _MAX_DOCUMENTS,
    ) -> None:
        if not isinstance(connections, Mapping) or not connections:
            raise ValueError('External Cosmos connections are required')
        if any(
            not isinstance(name, str)
            or _CONNECTION_NAME.fullmatch(name) is None
            or name in ('command-center', 'command_center')
            or not isinstance(client, CosmosClient)
            for name, client in connections.items()
        ):
            raise TypeError('Named Cosmos connections are invalid')
        if (
            type(max_documents_per_connection) is not int
            or not 1 <= max_documents_per_connection <= _MAX_DOCUMENTS
        ):
            raise ValueError('Discovery document limit is invalid')
        self._connections = dict(connections)
        self._max_documents = max_documents_per_connection

    def inspect(self) -> ToolCatalogDiscoveryReport:
        results = []
        for name, client in sorted(self._connections.items()):
            results.append(self._inspect_connection(name, client))
        return ToolCatalogDiscoveryReport(connections=tuple(results))

    def _inspect_connection(self, name: str, client: CosmosClient) -> ToolConnectionInspection:
        container = TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name
        try:
            candidates = client.query_items(
                container_name=container,
                query=_DISCOVERY_QUERY,
                parameters=(
                    CosmosQueryParameter(
                        name='@document_type', value=TOOL_PROJECTION_DOCUMENT_TYPE
                    ),
                    CosmosQueryParameter(name='@source_key', value=DEFAULT_TOOL_SOURCE_KEY.value),
                ),
                cross_partition=True,
                max_items=self._max_documents,
                page_size=min(self._max_documents, 100),
            )
        except CosmosContainerNotFoundError:
            return ToolConnectionInspection(name, ToolCatalogConnectionStatus.NO_CONTAINER)
        except CosmosResultLimitError:
            return _error(name, ToolCatalogDiscoveryIssue.LIMIT_EXCEEDED)
        except CosmosError:
            return _error(name, ToolCatalogDiscoveryIssue.QUERY_FAILED)
        if len(candidates) > self._max_documents:
            return _error(name, ToolCatalogDiscoveryIssue.LIMIT_EXCEEDED)
        if not candidates:
            return ToolConnectionInspection(name, ToolCatalogConnectionStatus.NO_TOOLS)
        seen: set[str] = set()
        tools: list[DiscoveredTool] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                return _error(name, ToolCatalogDiscoveryIssue.INVALID_DOCUMENT)
            namespace_key = candidate.get('partition_key')
            item_id = candidate.get('id')
            if not isinstance(item_id, str) or not item_id:
                return _error(name, ToolCatalogDiscoveryIssue.INVALID_DOCUMENT)
            namespace = _parse_namespace(namespace_key)
            if namespace is None:
                return _error(name, ToolCatalogDiscoveryIssue.INVALID_NAMESPACE)
            if namespace.scope_prefix in seen:
                return _error(name, ToolCatalogDiscoveryIssue.DUPLICATE_NAMESPACE)
            seen.add(namespace.scope_prefix)
            store = CosmosToolProjectionStore(
                client=client,
                settings=CosmosToolProjectionStoreSettings.from_namespace(
                    container_name=container,
                    namespace=namespace,
                ),
            )
            try:
                record = store.get_active(DEFAULT_TOOL_SOURCE_KEY)
            except ToolConfigurationProjectionError, CosmosError, TypeError, ValueError:
                return _error(name, ToolCatalogDiscoveryIssue.INVALID_PROJECTION)
            if record is None:
                return _error(name, ToolCatalogDiscoveryIssue.MISSING_PROJECTION)
            configuration = record.payload
            if not isinstance(configuration, ToolConfiguration):
                return _error(name, ToolCatalogDiscoveryIssue.INVALID_PROJECTION)
            if configuration.structure is None:
                return _error(name, ToolCatalogDiscoveryIssue.MISSING_STRUCTURE)
            tools.append(
                DiscoveredTool(
                    connection_name=name,
                    namespace_key=namespace.scope_prefix,
                    tool_key=configuration.tool_key,
                    display_name=configuration.display_name,
                    kind=configuration.kind.value,
                    source_release_id=record.source_release_id,
                    configuration=configuration,
                    projection_store=store,
                )
            )
        return ToolConnectionInspection(
            connection_name=name,
            status=ToolCatalogConnectionStatus.READY,
            tools=tuple(sorted(tools, key=lambda tool: (tool.tool_key, tool.namespace_key))),
        )


def _parse_namespace(value: object) -> StorageNamespace | None:
    if not isinstance(value, str) or value.count('/') != 1:
        return None
    application, tool = value.split('/')
    try:
        return StorageNamespace(application_namespace=application, scope_namespace=tool)
    except TypeError, ValueError:
        return None


def _error(name: str, issue: ToolCatalogDiscoveryIssue) -> ToolConnectionInspection:
    return ToolConnectionInspection(
        connection_name=name,
        status=ToolCatalogConnectionStatus.ERROR,
        issue=issue,
    )


class _PinnedToolProjectionStore(ProjectionStore[ToolConfiguration]):
    def __init__(self, tool: DiscoveredTool) -> None:
        self._tool = tool

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[ToolConfiguration] | None:
        record = self._tool.projection_store.get_active(source_key)
        if (
            record is None
            or record.source_release_id != self._tool.source_release_id
            or not isinstance(record.payload, ToolConfiguration)
            or record.payload.to_document() != self._tool.configuration.to_document()
        ):
            raise ToolCatalogDiscoveryError('Tool projection changed after discovery')
        return record

    def replace_active(
        self, projection: ProjectionRecord[ToolConfiguration]
    ) -> ProjectionRecord[ToolConfiguration]:
        raise ToolCatalogDiscoveryError('Discovery projection stores are read-only')
