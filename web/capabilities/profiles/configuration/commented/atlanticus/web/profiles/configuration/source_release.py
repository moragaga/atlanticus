from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationSourceError
from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
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

# El recurso de Profiles tiene identidad documental propia aunque use el Source genérico para versionado, historia y concurrencia.
PROFILES_SOURCE_DOCUMENT_TYPE = 'atlanticus_profiles_configuration_release'
PROFILES_SOURCE_SCHEMA_VERSION = 1
PROFILES_SOURCE_RESOURCE_PATH = 'profiles/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


# El payload publicado contiene sólo configuración Profiles y actor; no contiene Users, Access ni Navigation.
@dataclass(frozen=True, slots=True)
class ProfilesSourcePayload:
    configuration: ProfilesConfiguration
    published_by: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, ProfilesConfiguration):
            raise ProfilesConfigurationSourceError(
                'Profiles source configuration must be ProfilesConfiguration'
            )
        if not isinstance(self.published_by, str):
            raise ProfilesConfigurationSourceError('Profiles source publication actor must be text')
        actor = self.published_by.strip()
        if not actor:
            raise ProfilesConfigurationSourceError(
                'Profiles source publication actor must not be empty'
            )
        object.__setattr__(self, 'published_by', actor)


# La release conserva metadata genérica exact-release separada del payload funcional.
@dataclass(frozen=True, slots=True)
class ProfilesSourceRelease:
    metadata: SourceReleaseMetadata
    payload: ProfilesSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def configuration(self) -> ProfilesConfiguration:
        return self.payload.configuration

    @property
    def published_by(self) -> str:
        return self.payload.published_by


# El codec define la frontera durable propia de Profiles sin acoplarse al provider físico del SourceStore.
class ProfilesSourceCodec:
    def encode(
        self,
        *,
        configuration: ProfilesConfiguration,
        published_by: str,
    ) -> SourceResource:
        payload = ProfilesSourcePayload(
            configuration=configuration,
            published_by=published_by,
        )
        document = {
            'document_type': PROFILES_SOURCE_DOCUMENT_TYPE,
            'schema_version': PROFILES_SOURCE_SCHEMA_VERSION,
            'published_by': payload.published_by,
            'configuration': payload.configuration.to_document(),
        }
        # JSON compacto y gzip con mtime fijo producen bytes determinísticos para igual contenido.
        raw = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return SourceResource(
            logical_path=PROFILES_SOURCE_RESOURCE_PATH,
            content=gzip.compress(raw, mtime=0),
        )

    def decode(self, resources: tuple[SourceResource, ...]) -> ProfilesSourcePayload:
        # Una release Profiles válida posee exactamente un recurso de configuración propio.
        matches = tuple(
            resource
            for resource in resources
            if resource.logical_path == PROFILES_SOURCE_RESOURCE_PATH
        )
        if len(matches) != 1:
            raise ProfilesConfigurationSourceError(
                'Profiles source release must contain exactly one configuration resource'
            )
        document = _decode_document(matches[0].content)
        if document.get('document_type') != PROFILES_SOURCE_DOCUMENT_TYPE:
            raise ProfilesConfigurationSourceError(
                'Profiles source release document type is invalid'
            )
        if document.get('schema_version') != PROFILES_SOURCE_SCHEMA_VERSION:
            raise ProfilesConfigurationSourceError(
                'Profiles source release schema version is invalid'
            )
        try:
            configuration = document['configuration']
            published_by = document['published_by']
            if not isinstance(configuration, dict) or not isinstance(published_by, str):
                raise TypeError
            return ProfilesSourcePayload(
                configuration=ProfilesConfiguration.from_document(dict(configuration)),
                published_by=published_by,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ProfilesConfigurationSourceError(
                'Profiles source release contract is invalid'
            ) from error


# El servicio de dominio compone Profiles con SourceStore y conserva SourceKey inyectado por la composition.
class ProfilesSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: ProfilesSourceCodec | None = None,
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or ProfilesSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    def load_current(self) -> ProfilesSourceRelease | None:
        # Current selecciona la release exacta; el payload se relee usando esa identidad, no otra consulta implícita a current.
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> ProfilesSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        # Protegemos el boundary frente a un provider que devuelva metadata de otra fuente o release.
        if metadata.source_key != self._source_key:
            raise ProfilesConfigurationSourceError(
                'Profiles source store returned a different source key'
            )
        if metadata.release_ref != release_ref:
            raise ProfilesConfigurationSourceError(
                'Profiles source store returned a different source release'
            )
        return ProfilesSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_configuration(
        self,
        configuration: ProfilesConfiguration,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resource = self._codec.encode(
            configuration=configuration,
            published_by=published_by,
        )
        # El caller transporta explícitamente concurrencia y basis; Profiles no reconstruye identidad Source desde strings privadas.
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


# La descompresión está acotada para que un documento Source corrupto no pueda expandirse sin límite.
def _decode_document(payload: bytes) -> dict[str, Any]:
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise ProfilesConfigurationSourceError(
            'Profiles source release compressed payload is too large'
        )
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise ProfilesConfigurationSourceError(
            'Profiles source release payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise ProfilesConfigurationSourceError(
            'Profiles source release decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfilesConfigurationSourceError(
            'Profiles source release payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise ProfilesConfigurationSourceError(
            'Profiles source release payload root must be an object'
        )
    return document
