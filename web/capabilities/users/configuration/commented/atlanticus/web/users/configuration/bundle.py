# Espejo pedagógico del módulo productivo.
# Los comentarios explican responsabilidades sin alterar estructura ni comportamiento.
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog

BUNDLE_DOCUMENT_TYPE = 'atlanticus_users_configuration'
SOURCE_DOCUMENT_TYPE = 'atlanticus_users_configuration_source'
SCHEMA_VERSION = 2
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


# Define UsersConfigurationBundle como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UsersConfigurationBundle:
    catalog: UsersConfigurationCatalog
    revision: str
    saved_by: str
    saved_at_utc: datetime

    def __post_init__(self) -> None:
        expected = build_users_configuration_digest(self.catalog)
        actor = self.saved_by.strip()
        if self.revision.strip() != expected:
            raise UsersConfigurationValidationError(
                'Users configuration source revision does not match content'
            )
        if not actor:
            raise UsersConfigurationValidationError(
                'Users configuration source actor must not be empty'
            )
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise UsersConfigurationValidationError(
                'Users configuration source timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'saved_by', actor)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        catalog: UsersConfigurationCatalog,
        saved_by: str,
        now_utc: datetime | None = None,
    ) -> UsersConfigurationBundle:
        return cls(
            catalog=catalog,
            revision=build_users_configuration_digest(catalog),
            saved_by=saved_by,
            saved_at_utc=(now_utc or datetime.now(UTC)).astimezone(UTC),
        )

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': BUNDLE_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'revision': self.revision,
            'saved_by': self.saved_by,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'catalog': self.catalog.to_document(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfigurationBundle:
        if document.get('document_type') != BUNDLE_DOCUMENT_TYPE:
            raise UsersConfigurationValidationError('Users configuration document type is invalid')
        if document.get('schema_version') != SCHEMA_VERSION:
            raise UsersConfigurationValidationError('Users configuration schema version is invalid')
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return cls(
                catalog=UsersConfigurationCatalog.from_document(dict(catalog)),
                revision=str(document['revision']),
                saved_by=str(document['saved_by']),
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError(
                'Users configuration bundle contract is invalid'
            ) from error


# Define UsersConfigurationVersion como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UsersConfigurationVersion:
    catalog: UsersConfigurationCatalog
    revision: str
    created_by: str
    created_at_utc: datetime

    def __post_init__(self) -> None:
        expected = build_users_configuration_digest(self.catalog)
        actor = self.created_by.strip()
        if self.revision.strip() != expected:
            raise UsersConfigurationValidationError(
                'Users configuration version revision does not match content'
            )
        if not actor:
            raise UsersConfigurationValidationError(
                'Users configuration version actor must not be empty'
            )
        if self.created_at_utc.tzinfo is None or self.created_at_utc.utcoffset() is None:
            raise UsersConfigurationValidationError(
                'Users configuration version timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'created_by', actor)
        object.__setattr__(self, 'created_at_utc', self.created_at_utc.astimezone(UTC))

    @classmethod
    def from_bundle(cls, bundle: UsersConfigurationBundle) -> UsersConfigurationVersion:
        return cls(
            catalog=bundle.catalog,
            revision=bundle.revision,
            created_by=bundle.saved_by,
            created_at_utc=bundle.saved_at_utc,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'revision': self.revision,
            'created_by': self.created_by,
            'created_at_utc': self.created_at_utc.isoformat(),
            'catalog': self.catalog.to_document(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfigurationVersion:
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return cls(
                catalog=UsersConfigurationCatalog.from_document(dict(catalog)),
                revision=str(document['revision']),
                created_by=str(document['created_by']),
                created_at_utc=datetime.fromisoformat(str(document['created_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError(
                'Users configuration version contract is invalid'
            ) from error


# Define UsersConfigurationPublication como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UsersConfigurationPublication:
    revision: str
    published_by: str
    published_at_utc: datetime

    def __post_init__(self) -> None:
        revision = self.revision.strip()
        actor = self.published_by.strip()
        if not revision or not actor:
            raise UsersConfigurationValidationError(
                'Users configuration publication metadata must not be empty'
            )
        if self.published_at_utc.tzinfo is None or self.published_at_utc.utcoffset() is None:
            raise UsersConfigurationValidationError(
                'Users configuration publication timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', revision)
        object.__setattr__(self, 'published_by', actor)
        object.__setattr__(self, 'published_at_utc', self.published_at_utc.astimezone(UTC))

    def to_document(self) -> dict[str, object]:
        return {
            'revision': self.revision,
            'published_by': self.published_by,
            'published_at_utc': self.published_at_utc.isoformat(),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfigurationPublication:
        try:
            return cls(
                revision=str(document['revision']),
                published_by=str(document['published_by']),
                published_at_utc=datetime.fromisoformat(str(document['published_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError(
                'Users configuration publication contract is invalid'
            ) from error


# Define UsersConfigurationSourceDocument como frontera explícita del módulo y valida su contrato.
@dataclass(frozen=True, slots=True)
class UsersConfigurationSourceDocument:
    current_revision: str
    versions: tuple[UsersConfigurationVersion, ...]
    publications: tuple[UsersConfigurationPublication, ...]

    def __post_init__(self) -> None:
        current = self.current_revision.strip()
        versions = tuple(self.versions)
        publications = tuple(self.publications)
        version_keys = tuple(version.revision for version in versions)
        if not current:
            raise UsersConfigurationValidationError(
                'Users configuration current revision must not be empty'
            )
        if len(version_keys) != len(set(version_keys)):
            raise UsersConfigurationValidationError(
                'Users configuration versions must be unique by revision'
            )
        if current not in version_keys:
            raise UsersConfigurationValidationError(
                'Users configuration current revision is missing from versions'
            )
        if not publications or publications[-1].revision != current:
            raise UsersConfigurationValidationError(
                'Users configuration current publication metadata is invalid'
            )
        if any(publication.revision not in version_keys for publication in publications):
            raise UsersConfigurationValidationError(
                'Users configuration publication references an unknown revision'
            )
        object.__setattr__(self, 'current_revision', current)
        object.__setattr__(self, 'versions', versions)
        object.__setattr__(self, 'publications', publications)

    @classmethod
    def from_bundle(cls, bundle: UsersConfigurationBundle) -> UsersConfigurationSourceDocument:
        return cls(
            current_revision=bundle.revision,
            versions=(UsersConfigurationVersion.from_bundle(bundle),),
            publications=(
                UsersConfigurationPublication(
                    revision=bundle.revision,
                    published_by=bundle.saved_by,
                    published_at_utc=bundle.saved_at_utc,
                ),
            ),
        )

    def publish(self, bundle: UsersConfigurationBundle) -> UsersConfigurationSourceDocument:
        if self.current_revision == bundle.revision:
            return self
        versions = self.versions
        if bundle.revision not in {version.revision for version in versions}:
            versions = (*versions, UsersConfigurationVersion.from_bundle(bundle))
        publications = (
            *self.publications,
            UsersConfigurationPublication(
                revision=bundle.revision,
                published_by=bundle.saved_by,
                published_at_utc=bundle.saved_at_utc,
            ),
        )
        return UsersConfigurationSourceDocument(
            current_revision=bundle.revision,
            versions=versions,
            publications=publications,
        )

    def current_bundle(self) -> UsersConfigurationBundle:
        return self.require_revision(self.current_revision)

    def require_revision(self, revision: str) -> UsersConfigurationBundle:
        normalized = revision.strip()
        versions = {version.revision: version for version in self.versions}
        try:
            version = versions[normalized]
        except KeyError as error:
            raise UsersConfigurationValidationError(
                'Users configuration revision does not exist'
            ) from error
        publications = [item for item in self.publications if item.revision == normalized]
        audit = publications[-1]
        return UsersConfigurationBundle(
            catalog=version.catalog,
            revision=version.revision,
            saved_by=audit.published_by,
            saved_at_utc=audit.published_at_utc,
        )

    def list_history(self, *, limit: int = 20) -> tuple[UsersConfigurationBundle, ...]:
        if limit < 1:
            return ()
        ordered = list(reversed(self.publications))
        seen: set[str] = set()
        result: list[UsersConfigurationBundle] = []
        for publication in ordered:
            if publication.revision in seen:
                continue
            seen.add(publication.revision)
            result.append(self.require_revision(publication.revision))
            if len(result) >= limit:
                break
        return tuple(result)

    def fetch_revision(self, revision: str) -> UsersConfigurationBundle | None:
        normalized = revision.strip()
        if normalized not in {version.revision for version in self.versions}:
            return None
        return self.require_revision(normalized)

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': SOURCE_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'current_revision': self.current_revision,
            'versions': [version.to_document() for version in self.versions],
            'publications': [publication.to_document() for publication in self.publications],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersConfigurationSourceDocument:
        if document.get('document_type') != SOURCE_DOCUMENT_TYPE:
            raise UsersConfigurationValidationError(
                'Users configuration source document type is invalid'
            )
        if document.get('schema_version') != SCHEMA_VERSION:
            raise UsersConfigurationValidationError(
                'Users configuration source schema version is invalid'
            )
        try:
            raw_versions = document['versions']
            raw_publications = document['publications']
            if not isinstance(raw_versions, list) or not isinstance(raw_publications, list):
                raise TypeError
            return cls(
                current_revision=str(document['current_revision']),
                versions=tuple(
                    UsersConfigurationVersion.from_document(dict(item))
                    for item in raw_versions
                ),
                publications=tuple(
                    UsersConfigurationPublication.from_document(dict(item))
                    for item in raw_publications
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise UsersConfigurationValidationError(
                'Users configuration source contract is invalid'
            ) from error


# Encapsula la operación build users configuration digest para mantener esta responsabilidad aislada.
def build_users_configuration_digest(catalog: UsersConfigurationCatalog) -> str:
    canonical = json.dumps(
        catalog.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


# Encapsula la operación encode users configuration source para mantener esta responsabilidad aislada.
def encode_users_configuration_source(source: UsersConfigurationSourceDocument) -> bytes:
    return _encode_document(source.to_document())


# Encapsula la operación decode users configuration source para mantener esta responsabilidad aislada.
def decode_users_configuration_source(payload: bytes) -> UsersConfigurationSourceDocument:
    return UsersConfigurationSourceDocument.from_document(_decode_document(payload))


# Encapsula la operación encode users configuration bundle para mantener esta responsabilidad aislada.
def encode_users_configuration_bundle(bundle: UsersConfigurationBundle) -> bytes:
    return _encode_document(bundle.to_document())


# Encapsula la operación decode users configuration import para mantener esta responsabilidad aislada.
def decode_users_configuration_import(payload: bytes) -> UsersConfigurationCatalog:
    document = _decode_document(payload)
    document_type = document.get('document_type')
    if document_type == SOURCE_DOCUMENT_TYPE:
        return UsersConfigurationSourceDocument.from_document(document).current_bundle().catalog
    if document_type == BUNDLE_DOCUMENT_TYPE:
        return UsersConfigurationBundle.from_document(document).catalog
    raise UsersConfigurationValidationError('Users configuration import document type is invalid')


# Encapsula la operación encode document para mantener esta responsabilidad aislada.
def _encode_document(document: dict[str, object]) -> bytes:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return gzip.compress(canonical, compresslevel=9, mtime=0)


# Encapsula la operación decode document para mantener esta responsabilidad aislada.
def _decode_document(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise UsersConfigurationValidationError('Users configuration file must not be empty')
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise UsersConfigurationValidationError('Users configuration file exceeds the size limit')
    if payload[:2] != b'\x1f\x8b':
        raise UsersConfigurationValidationError('Users configuration file must be gzip encoded')
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as compressed:
            decoded = compressed.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except (OSError, EOFError) as error:
        raise UsersConfigurationValidationError(
            'Users configuration gzip content is invalid'
        ) from error
    if len(decoded) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise UsersConfigurationValidationError(
            'Users configuration decompressed content exceeds the size limit'
        )
    try:
        document = json.loads(decoded.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsersConfigurationValidationError(
            'Users configuration must contain valid UTF-8 JSON'
        ) from error
    if not isinstance(document, dict):
        raise UsersConfigurationValidationError('Users configuration root must be an object')
    return document
