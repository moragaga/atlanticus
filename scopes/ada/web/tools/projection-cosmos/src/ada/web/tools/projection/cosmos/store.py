from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.projection_record import (
    tool_projection_from_document,
    tool_projection_to_document,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey


@dataclass(frozen=True, slots=True)
class CosmosToolProjectionStoreSettings:
    container_name: str
    namespace_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'container_name',
            _required_clean_text(
                self.container_name,
                'container_name',
            ),
        )
        object.__setattr__(
            self,
            'namespace_key',
            _required_namespace_key(self.namespace_key),
        )

    @classmethod
    def from_namespace(
        cls,
        *,
        container_name: str,
        namespace: AdaStorageNamespace,
    ) -> CosmosToolProjectionStoreSettings:
        if not isinstance(namespace, AdaStorageNamespace):
            raise TypeError('namespace must be AdaStorageNamespace')
        return cls(
            container_name=container_name,
            namespace_key=namespace.tool_prefix,
        )


class CosmosToolProjectionStore(ProjectionStore[ToolConfiguration]):
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosToolProjectionStoreSettings,
    ) -> None:
        if not isinstance(settings, CosmosToolProjectionStoreSettings):
            raise TypeError('settings must be CosmosToolProjectionStoreSettings')
        self._client = client
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[ToolConfiguration] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(
                    self._settings.namespace_key,
                    source_key,
                ),
                partition_key=self._settings.namespace_key,
            )
        except CosmosError as error:
            raise ToolConfigurationProjectionError(
                'Could not read Cosmos Tool projection'
            ) from error
        if document is None:
            return None
        projection = tool_projection_from_document(document)
        if projection.source_key != source_key:
            raise ToolConfigurationProjectionError(
                'Cosmos Tool projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[ToolConfiguration],
    ) -> ProjectionRecord[ToolConfiguration]:
        document = tool_projection_to_document(
            projection,
            item_id=_cosmos_item_id(
                self._settings.namespace_key,
                projection.source_key,
            ),
            partition_key=self._settings.namespace_key,
        )
        try:
            saved = self._client.upsert_item(
                container_name=self._settings.container_name,
                item=document,
            )
        except CosmosError as error:
            raise ToolConfigurationProjectionError(
                'Could not write Cosmos Tool projection'
            ) from error
        persisted = tool_projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise ToolConfigurationProjectionError(
                'Cosmos Tool projection persisted a different source key'
            )
        return persisted


def _cosmos_item_id(
    namespace_key: str,
    source_key: SourceKey,
) -> str:
    identity = f'{namespace_key}\x00{source_key.value}'.encode('utf-8')
    digest = hashlib.sha256(identity).hexdigest()
    return f'ada-tool-projection-{digest}'


def _required_clean_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    if not value or not value.strip() or value != value.strip():
        raise ValueError(f'{field_name} has an invalid format')
    if '\x00' in value:
        raise ValueError(f'{field_name} has an invalid format')
    return value


def _required_namespace_key(value: object) -> str:
    normalized = _required_clean_text(value, 'namespace_key')
    if (
        normalized.startswith('/')
        or normalized.endswith('/')
        or '//' in normalized
        or any(part in {'.', '..'} for part in normalized.split('/'))
    ):
        raise ValueError('namespace_key has an invalid format')
    return normalized
