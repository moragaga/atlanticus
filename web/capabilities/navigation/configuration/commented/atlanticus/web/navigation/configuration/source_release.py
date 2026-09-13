# Este módulo define el handoff de Navigation hacia Source Core sin reimplementar releases ni concurrencia.
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationSourceError,
    NavigationConfigurationValidationError,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
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
# El documento de dominio vive dentro de una release de Source; la identidad de release queda fuera del payload.
)
from atlanticus.web.source.store import SourceStore

NAVIGATION_SOURCE_DOCUMENT_TYPE = 'atlanticus_navigation_configuration_release'
NAVIGATION_SOURCE_SCHEMA_VERSION = 1
NAVIGATION_SOURCE_RESOURCE_PATH = 'navigation/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024

# El actor pertenece a la metadata de dominio y nunca se usa como identidad durable de Source.

@dataclass(frozen=True, slots=True)
class NavigationSourcePayload:
    catalog: NavigationConfigurationCatalog
    published_by: str

    def __post_init__(self) -> None:
        actor = self.published_by.strip()
        if not actor:
            raise NavigationConfigurationSourceError(
                'Navigation source publication actor must not be empty'
            )
        object.__setattr__(self, 'published_by', actor)


# Esta vista combina metadata canónica de Source con el payload Navigation leído desde esa release exacta.
@dataclass(frozen=True, slots=True)
class NavigationSourceRelease:
    metadata: SourceReleaseMetadata
    payload: NavigationSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def catalog(self) -> NavigationConfigurationCatalog:
        return self.payload.catalog

    @property
    def published_by(self) -> str:
        return self.payload.published_by

# El codec produce JSON canónico compacto y gzip determinista; Storage sólo recibe bytes del recurso.

class NavigationSourceCodec:
    def encode(
        self,
        *,
        catalog: NavigationConfigurationCatalog,
        published_by: str,
    ) -> SourceResource:
        payload = NavigationSourcePayload(catalog=catalog, published_by=published_by)
        document = {
            'document_type': NAVIGATION_SOURCE_DOCUMENT_TYPE,
            'schema_version': NAVIGATION_SOURCE_SCHEMA_VERSION,
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
            logical_path=NAVIGATION_SOURCE_RESOURCE_PATH,
            content=gzip.compress(raw, mtime=0),
        )
# Al decodificar buscamos el recurso lógico conocido y toleramos que futuras releases agreguen otros recursos.

    def decode(self, resources: tuple[SourceResource, ...]) -> NavigationSourcePayload:
        matches = tuple(
            resource
            for resource in resources
            if resource.logical_path == NAVIGATION_SOURCE_RESOURCE_PATH
        )
        if len(matches) != 1:
            raise NavigationConfigurationSourceError(
                'Navigation source release must contain exactly one configuration resource'
            )
        document = _decode_document(matches[0].content)
        if document.get('document_type') != NAVIGATION_SOURCE_DOCUMENT_TYPE:
            raise NavigationConfigurationSourceError(
                'Navigation source release document type is invalid'
            )
        if document.get('schema_version') != NAVIGATION_SOURCE_SCHEMA_VERSION:
            raise NavigationConfigurationSourceError(
                'Navigation source release schema version is invalid'
            )
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return NavigationSourcePayload(
                catalog=NavigationConfigurationCatalog.from_document(dict(catalog)),
                published_by=str(document['published_by']),
            )
        except (KeyError, TypeError, ValueError, NavigationConfigurationValidationError) as error:
            raise NavigationConfigurationSourceError(
                'Navigation source release contract is invalid'
            ) from error


class NavigationSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: NavigationSourceCodec | None = None,
# El servicio coordina el dominio con SourceStore; no decide CAS ni genera SourceReleaseId.
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or NavigationSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    def load_current(self) -> NavigationSourceRelease | None:
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> NavigationSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        if metadata.source_key != self._source_key:
            raise NavigationConfigurationSourceError(
                'Navigation source store returned a different source key'
# La hidratación parte de un snapshot y luego lee esa release exacta, aunque current avance después.
            )
        if metadata.release_ref != release_ref:
            raise NavigationConfigurationSourceError(
                'Navigation source store returned a different source release'
            )
        return NavigationSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_catalog(
        self,
        catalog: NavigationConfigurationCatalog,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resource = self._codec.encode(catalog=catalog, published_by=published_by)
        return self._source.publish(
            PublishRequest(
                source_key=self._source_key,
# Publicar siempre invoca SourceStore.publish; no existe no-op por hash de contenido en Navigation.
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

# History proviene exclusivamente de Source Core, no de una lista embebida dentro del JSON Navigation.

def _decode_document(payload: bytes) -> dict[str, Any]:
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise NavigationConfigurationSourceError(
            'Navigation source release compressed payload is too large'
        )
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise NavigationConfigurationSourceError(
            'Navigation source release payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
# La descompresión está acotada para evitar aceptar payloads comprimidos o expandidos fuera del contrato.
        raise NavigationConfigurationSourceError(
            'Navigation source release decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NavigationConfigurationSourceError(
            'Navigation source release payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise NavigationConfigurationSourceError(
            'Navigation source release payload root must be an object'
        )
    return document
