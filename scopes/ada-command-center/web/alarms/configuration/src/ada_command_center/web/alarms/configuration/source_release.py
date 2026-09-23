from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationSourceError
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

ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE = 'ada_command_center_alarm_configuration_release'
ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION = 2
ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH = 'alarms/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AlarmConfigurationSourcePayload:
    snapshot: AlarmConfigurationSnapshot
    published_by: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, AlarmConfigurationSnapshot):
            raise AlarmConfigurationSourceError('Alarm Configuration source snapshot is invalid')
        actor = self.published_by.strip() if isinstance(self.published_by, str) else ''
        if not actor:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration publication actor must not be empty'
            )
        object.__setattr__(self, 'published_by', actor)


@dataclass(frozen=True, slots=True)
class AlarmConfigurationSourceRelease:
    metadata: SourceReleaseMetadata
    payload: AlarmConfigurationSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def snapshot(self) -> AlarmConfigurationSnapshot:
        return self.payload.snapshot

    @property
    def published_by(self) -> str:
        return self.payload.published_by


class AlarmConfigurationSourceCodec:
    def encode(
        self,
        *,
        snapshot: AlarmConfigurationSnapshot,
        published_by: str,
    ) -> SourceResource:
        payload = AlarmConfigurationSourcePayload(
            snapshot=snapshot,
            published_by=published_by,
        )
        document = {
            'document_type': ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE,
            'schema_version': ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION,
            'published_by': payload.published_by,
            'snapshot': payload.snapshot.to_document(),
        }
        raw = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return SourceResource(
            logical_path=ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH,
            content=gzip.compress(raw, mtime=0),
        )

    def decode(self, resources: tuple[SourceResource, ...]) -> AlarmConfigurationSourcePayload:
        matches = tuple(
            resource
            for resource in resources
            if resource.logical_path == ALARM_CONFIGURATION_SOURCE_RESOURCE_PATH
        )
        if len(matches) != 1:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source release must contain exactly one configuration resource'
            )
        document = _decode_document(matches[0].content)
        if document.get('document_type') != ALARM_CONFIGURATION_SOURCE_DOCUMENT_TYPE:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source document type is invalid'
            )
        if document.get('schema_version') != ALARM_CONFIGURATION_SOURCE_SCHEMA_VERSION:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source schema version is invalid'
            )
        try:
            snapshot = document['snapshot']
            if not isinstance(snapshot, dict):
                raise TypeError
            return AlarmConfigurationSourcePayload(
                snapshot=AlarmConfigurationSnapshot.from_document(snapshot),
                published_by=str(document['published_by']),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source contract is invalid'
            ) from error


class AlarmConfigurationSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: AlarmConfigurationSourceCodec | None = None,
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or AlarmConfigurationSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    def load_current(self) -> AlarmConfigurationSourceRelease | None:
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> AlarmConfigurationSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        if metadata.source_key != self._source_key:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source returned a different source key'
            )
        if metadata.release_ref != release_ref:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source returned a different source release'
            )
        return AlarmConfigurationSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_snapshot(
        self,
        snapshot: AlarmConfigurationSnapshot,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resource = self._codec.encode(
            snapshot=snapshot,
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
        raise AlarmConfigurationSourceError(
            'Alarm Configuration source compressed payload is too large'
        )
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise AlarmConfigurationSourceError(
            'Alarm Configuration source payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise AlarmConfigurationSourceError(
            'Alarm Configuration source decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AlarmConfigurationSourceError(
            'Alarm Configuration source payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise AlarmConfigurationSourceError(
            'Alarm Configuration source payload root must be an object'
        )
    return document
