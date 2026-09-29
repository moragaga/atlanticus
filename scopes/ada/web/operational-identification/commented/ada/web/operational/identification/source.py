# El Source durable se publica mediante SourceStore de Atlanticus, inyectado como Blob o Local para pruebas.
from __future__ import annotations

import gzip
import json
from io import BytesIO

from ada.web.operational.identification.errors import OperationalIdentificationError
from ada.web.operational.identification.keys import (
    CATALOG_SOURCE_KEY,
    assignment_source_key,
    source_kind,
)
from ada.web.operational.identification.models import (
    OperationalAssignment,
    OperationalCatalog,
    OperationalDocument,
    parse_document,
)
from atlanticus.web.source.models import (
    HistoryPage,
    HistoryQuery,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore

_RESOURCE = 'operational/data.json.gz'
_DOCUMENT_TYPE = 'ada_operational_source'
_MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
_MAX_RAW_BYTES = 4 * 1024 * 1024


# Serialización determinista y comprimida de releases de catálogo y de usuario.
class OperationalSourceCodec:
    def encode(self, payload: OperationalDocument, *, actor: str) -> SourceResource:
        if not isinstance(payload, (OperationalCatalog, OperationalAssignment)):
            raise TypeError('Operational source payload has an invalid type')
        if (
            not isinstance(actor, str)
            or not actor.strip()
            or actor != actor.strip()
            or len(actor) > 128
            or any(ord(char) < 32 for char in actor)
        ):
            raise OperationalIdentificationError('Operational publication actor is invalid')
        kind = 'catalog' if isinstance(payload, OperationalCatalog) else 'assignment'
        raw = json.dumps(
            {
                'document_type': _DOCUMENT_TYPE,
                'schema_version': 1,
                'kind': kind,
                'actor': actor,
                'payload': payload.to_document(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        if len(raw) > _MAX_RAW_BYTES:
            raise OperationalIdentificationError('Operational source payload exceeds limit')
        compressed = gzip.compress(raw, mtime=0)
        if len(compressed) > _MAX_COMPRESSED_BYTES:
            raise OperationalIdentificationError('Operational source payload exceeds limit')
        return SourceResource(logical_path=_RESOURCE, content=compressed)

    def decode(self, resources: tuple[SourceResource, ...]) -> OperationalDocument:
        if len(resources) != 1 or resources[0].logical_path != _RESOURCE:
            raise OperationalIdentificationError('Operational source release resources are invalid')
        payload = resources[0].content
        if len(payload) > _MAX_COMPRESSED_BYTES:
            raise OperationalIdentificationError('Operational source payload exceeds limit')
        try:
            with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
                raw = stream.read(_MAX_RAW_BYTES + 1)
            if len(raw) > _MAX_RAW_BYTES:
                raise OperationalIdentificationError('Operational source payload exceeds limit')
            data = json.loads(raw.decode('utf-8'))
        except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as error:
            raise OperationalIdentificationError('Operational source payload is invalid') from error
        if not isinstance(data, dict) or set(data) != {
            'document_type',
            'schema_version',
            'kind',
            'actor',
            'payload',
        }:
            raise OperationalIdentificationError('Operational source schema is invalid')
        if data['document_type'] != _DOCUMENT_TYPE or data['schema_version'] != 1:
            raise OperationalIdentificationError('Operational source schema is invalid')
        if (
            not isinstance(data['actor'], str)
            or not data['actor'].strip()
            or data['actor'] != data['actor'].strip()
            or len(data['actor']) > 128
            or any(ord(char) < 32 for char in data['actor'])
        ):
            raise OperationalIdentificationError('Operational source actor is invalid')
        if not isinstance(data['payload'], dict):
            raise OperationalIdentificationError('Operational source payload is invalid')
        return parse_document(data['kind'], data['payload'])


# Cada usuario posee su SourceKey y su historial independiente con concurrencia de SourceStore.
class OperationalSourceService:
    def __init__(self, *, store: SourceStore, codec: OperationalSourceCodec | None = None) -> None:
        self._store = store
        self._codec = codec or OperationalSourceCodec()

    def snapshot(self, source_key: SourceKey) -> SourceSnapshot:
        source_kind(source_key)
        return self._store.get_current(source_key)

    def read(self, source_key: SourceKey, release: SourceReleaseRef) -> OperationalDocument:
        kind, user_id = source_kind(source_key)
        metadata, resources = self._store.read_release(source_key, release)
        if metadata.source_key != source_key or metadata.release_ref != release:
            raise OperationalIdentificationError('Operational source release identity mismatch')
        value = self._codec.decode(resources)
        if (kind == 'catalog' and not isinstance(value, OperationalCatalog)) or (
            kind == 'assignment'
            and (not isinstance(value, OperationalAssignment) or value.user_id != user_id)
        ):
            raise OperationalIdentificationError('Operational source release payload mismatch')
        return value

    # La edición parte del estado durable, no de una proyección potencialmente rezagada.
    def current(self, source_key: SourceKey) -> tuple[SourceSnapshot, OperationalDocument | None]:
        snapshot = self.snapshot(source_key)
        if snapshot.current is None:
            return snapshot, None
        return snapshot, self.read(source_key, snapshot.current.release_ref)

    # Se publica solamente el Source; un fallo posterior de Cosmos puede reintentarse.
    def publish(
        self,
        payload: OperationalDocument,
        *,
        actor: str,
        expected: SourceSnapshot,
    ) -> PublishResult:
        source_key = (
            CATALOG_SOURCE_KEY
            if isinstance(payload, OperationalCatalog)
            else assignment_source_key(payload.user_id)
        )
        if expected.source_key != source_key:
            raise OperationalIdentificationError(
                'Operational source expectation has a different key'
            )
        return self._store.publish(
            PublishRequest(
                source_key=source_key,
                resources=(self._codec.encode(payload, actor=actor),),
                expected_concurrency_token=expected.concurrency_token,
                basis_release=(
                    expected.current.release_ref if expected.current is not None else None
                ),
            )
        )

    def history(self, source_key: SourceKey, *, limit: int = 20) -> HistoryPage:
        source_kind(source_key)
        return self._store.query_history(HistoryQuery(source_key=source_key, page_size=limit))
