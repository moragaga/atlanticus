from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from ada.web.tools.configuration.errors import ToolConfigurationSourceError
from ada.web.tools.configuration.models import ToolConfiguration
from atlanticus.web.source.models import (
    ConcurrencyToken,
    HistoryPage,
    HistoryQuery,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore

TOOL_SOURCE_DOCUMENT_TYPE = 'ada_tool_configuration_release'
TOOL_SOURCE_SCHEMA_VERSION = 1
TOOL_SOURCE_RESOURCE_PATH = 'tools/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ToolSourcePayload:
    configuration: ToolConfiguration
    published_by: str

    def __post_init__(self) -> None:
        actor = self.published_by.strip()
        if not actor:
            raise ToolConfigurationSourceError('Tool source publication actor must not be empty')
        object.__setattr__(self, 'published_by', actor)


@dataclass(frozen=True, slots=True)
class ToolSourceRelease:
    metadata: SourceReleaseMetadata
    payload: ToolSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def configuration(self) -> ToolConfiguration:
        return self.payload.configuration

    @property
    def published_by(self) -> str:
        return self.payload.published_by


class ToolSourceCodec:
    def encode(
        self,
        *,
        configuration: ToolConfiguration,
        published_by: str,
    ) -> SourceResource:
        payload = ToolSourcePayload(configuration=configuration, published_by=published_by)
        document = {
            'document_type': TOOL_SOURCE_DOCUMENT_TYPE,
            'schema_version': TOOL_SOURCE_SCHEMA_VERSION,
            'published_by': payload.published_by,
            'configuration': payload.configuration.to_document(),
        }
        raw = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return SourceResource(
            logical_path=TOOL_SOURCE_RESOURCE_PATH,
            content=gzip.compress(raw, mtime=0),
        )

    def decode(self, resources: tuple[SourceResource, ...]) -> ToolSourcePayload:
        matches = tuple(
            resource
            for resource in resources
            if resource.logical_path == TOOL_SOURCE_RESOURCE_PATH
        )
        if len(matches) != 1:
            raise ToolConfigurationSourceError(
                'Tool source release must contain exactly one configuration resource'
            )
        document = _decode_document(matches[0].content)
        if document.get('document_type') != TOOL_SOURCE_DOCUMENT_TYPE:
            raise ToolConfigurationSourceError('Tool source release document type is invalid')
        if document.get('schema_version') != TOOL_SOURCE_SCHEMA_VERSION:
            raise ToolConfigurationSourceError('Tool source release schema version is invalid')
        try:
            configuration = document['configuration']
            if not isinstance(configuration, dict):
                raise TypeError
            return ToolSourcePayload(
                configuration=ToolConfiguration.from_document(configuration),
                published_by=str(document['published_by']),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ToolConfigurationSourceError('Tool source release contract is invalid') from error


class ToolSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: ToolSourceCodec | None = None,
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or ToolSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    def load_current(self) -> ToolSourceRelease | None:
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> ToolSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        if metadata.source_key != self._source_key:
            raise ToolConfigurationSourceError('Tool source store returned a different source key')
        if metadata.release_ref != release_ref:
            raise ToolConfigurationSourceError('Tool source store returned a different source release')
        return ToolSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_configuration(
        self,
        configuration: ToolConfiguration,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resource = self._codec.encode(
            configuration=configuration,
            published_by=published_by,
        )
        return self._source.publish(
            PublishRequest(
                source_key=self._source_key,
                resources=(resource,),
                expected_concurrency_token=expected_concurrency_token,
                basis_release=basis_release,
            )
        )

    def query_history(
        self,
        *,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> HistoryPage:
        return self._source.query_history(
            HistoryQuery(
                source_key=self._source_key,
                page_size=page_size,
                cursor=cursor,
            )
        )


def _decode_document(payload: bytes) -> dict[str, Any]:
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise ToolConfigurationSourceError('Tool source release compressed payload is too large')
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise ToolConfigurationSourceError(
            'Tool source release payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise ToolConfigurationSourceError('Tool source release decompressed payload is too large')
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolConfigurationSourceError(
            'Tool source release payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise ToolConfigurationSourceError('Tool source release payload root must be an object')
    return document
