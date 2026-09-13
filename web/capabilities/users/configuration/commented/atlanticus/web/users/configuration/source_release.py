# Este módulo conecta Users con Source Core sin volver a implementar releases, History ni CAS.
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

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
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationSourceError,
    UsersConfigurationValidationError,
)
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog

# El recurso de dominio es estable; la identidad de publicación pertenece a SourceReleaseRef.
USERS_SOURCE_DOCUMENT_TYPE = 'atlanticus_users_configuration_release'
USERS_SOURCE_SCHEMA_VERSION = 1
USERS_SOURCE_RESOURCE_PATH = 'users/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


# El actor es metadata funcional del dominio, no reemplaza la metadata durable de Source.
@dataclass(frozen=True, slots=True)
class UsersSourcePayload:
    catalog: UsersConfigurationCatalog
    published_by: str

    def __post_init__(self) -> None:
        actor = self.published_by.strip()
        if not actor:
            raise UsersConfigurationSourceError('Users source publication actor must not be empty')
        object.__setattr__(self, 'published_by', actor)


# La vista de una release combina metadata canónica de Source con el payload Users decodificado.
@dataclass(frozen=True, slots=True)
class UsersSourceRelease:
    metadata: SourceReleaseMetadata
    payload: UsersSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def catalog(self) -> UsersConfigurationCatalog:
        return self.payload.catalog

    @property
    def published_by(self) -> str:
        return self.payload.published_by


# El codec genera JSON compacto y gzip determinista para que el contenido sea estable.
class UsersSourceCodec:
    def encode(
        self,
        *,
        catalog: UsersConfigurationCatalog,
        published_by: str,
    ) -> SourceResource:
        payload = UsersSourcePayload(catalog=catalog, published_by=published_by)
        document = {
            'document_type': USERS_SOURCE_DOCUMENT_TYPE,
            'schema_version': USERS_SOURCE_SCHEMA_VERSION,
            'published_by': payload.published_by,
            'catalog': payload.catalog.to_document(),
        }
        raw = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return SourceResource(
            logical_path=USERS_SOURCE_RESOURCE_PATH,
            content=gzip.compress(raw, mtime=0),
        )

    # Una release puede agregar otros recursos en el futuro, pero el recurso Users debe existir
# una sola vez.
    def decode(self, resources: tuple[SourceResource, ...]) -> UsersSourcePayload:
        matches = tuple(
            resource
            for resource in resources
            if resource.logical_path == USERS_SOURCE_RESOURCE_PATH
        )
        if len(matches) != 1:
            raise UsersConfigurationSourceError(
                'Users source release must contain exactly one configuration resource'
            )
        document = _decode_document(matches[0].content)
        if document.get('document_type') != USERS_SOURCE_DOCUMENT_TYPE:
            raise UsersConfigurationSourceError('Users source release document type is invalid')
        if document.get('schema_version') != USERS_SOURCE_SCHEMA_VERSION:
            raise UsersConfigurationSourceError('Users source release schema version is invalid')
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return UsersSourcePayload(
                catalog=UsersConfigurationCatalog.from_document(dict(catalog)),
                published_by=str(document['published_by']),
            )
        except (KeyError, TypeError, ValueError, UsersConfigurationValidationError) as error:
            raise UsersConfigurationSourceError(
                'Users source release contract is invalid'
            ) from error


# El servicio es una fachada de dominio: SourceStore sigue siendo owner de publicación,
# concurrencia e History.
class UsersSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: UsersSourceCodec | None = None,
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or UsersSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    # El snapshot selecciona una release exacta; load_release no vuelve a consultar current.
    def load_current(self) -> UsersSourceRelease | None:
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> UsersSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        if metadata.source_key != self._source_key:
            raise UsersConfigurationSourceError(
                'Users source store returned a different source key'
            )
        if metadata.release_ref != release_ref:
            raise UsersConfigurationSourceError(
                'Users source store returned a different source release'
            )
        return UsersSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_catalog(
        self,
        catalog: UsersConfigurationCatalog,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resource = self._codec.encode(catalog=catalog, published_by=published_by)
        # Incluso contenido idéntico puede crear otra publicación; el no-op no pertenece a
        # SourceStore.
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
        # History se delega a Source Core y nunca se reconstruye desde el documento legacy de Users.
        return self._source.query_history(
            HistoryQuery(
                source_key=self._source_key,
                page_size=page_size,
                cursor=cursor,
            )
        )


def _decode_document(payload: bytes) -> dict[str, Any]:
    # Ambos límites protegen el contrato frente a payloads comprimidos o expandidos excesivos.
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise UsersConfigurationSourceError('Users source release compressed payload is too large')
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise UsersConfigurationSourceError(
            'Users source release payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise UsersConfigurationSourceError(
            'Users source release decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsersConfigurationSourceError(
            'Users source release payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise UsersConfigurationSourceError('Users source release payload root must be an object')
    return document
