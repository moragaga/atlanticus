from __future__ import annotations

# El bundle versiona el contrato persistido de Navigation de forma independiente del runtime.


import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationValidationError
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog

BUNDLE_DOCUMENT_TYPE = 'atlanticus_navigation_configuration'
SOURCE_DOCUMENT_TYPE = 'atlanticus_navigation_configuration_source'
SCHEMA_VERSION = 2
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class NavigationConfigurationBundle:
    catalog: NavigationConfigurationCatalog
    revision: str
    saved_by: str
    saved_at_utc: datetime

    def __post_init__(self) -> None:
        expected = build_navigation_configuration_digest(self.catalog)
        actor = self.saved_by.strip()
        if self.revision.strip() != expected:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source revision does not match content'
            )
        if not actor:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source actor must not be empty'
            )
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'saved_by', actor)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        catalog: NavigationConfigurationCatalog,
        saved_by: str,
        now_utc: datetime | None = None,
    ) -> NavigationConfigurationBundle:
        return cls(
            catalog=catalog,
            revision=build_navigation_configuration_digest(catalog),
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
    def from_document(cls, document: dict[str, Any]) -> NavigationConfigurationBundle:
        if document.get('document_type') != BUNDLE_DOCUMENT_TYPE:
            raise NavigationConfigurationValidationError(
                'Navigation configuration document type is invalid'
            )
        if document.get('schema_version') != SCHEMA_VERSION:
            raise NavigationConfigurationValidationError(
                'Navigation configuration schema version is invalid'
            )
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return cls(
                catalog=NavigationConfigurationCatalog.from_document(dict(catalog)),
                revision=str(document['revision']),
                saved_by=str(document['saved_by']),
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration bundle contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationConfigurationVersion:
    catalog: NavigationConfigurationCatalog
    revision: str
    created_by: str
    created_at_utc: datetime

    def __post_init__(self) -> None:
        expected = build_navigation_configuration_digest(self.catalog)
        actor = self.created_by.strip()
        if self.revision.strip() != expected:
            raise NavigationConfigurationValidationError(
                'Navigation configuration version revision does not match content'
            )
        if not actor:
            raise NavigationConfigurationValidationError(
                'Navigation configuration version actor must not be empty'
            )
        if self.created_at_utc.tzinfo is None or self.created_at_utc.utcoffset() is None:
            raise NavigationConfigurationValidationError(
                'Navigation configuration version timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected)
        object.__setattr__(self, 'created_by', actor)
        object.__setattr__(self, 'created_at_utc', self.created_at_utc.astimezone(UTC))

    @classmethod
    def from_bundle(
        cls,
        bundle: NavigationConfigurationBundle,
    ) -> NavigationConfigurationVersion:
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
    def from_document(cls, document: dict[str, Any]) -> NavigationConfigurationVersion:
        try:
            catalog = document['catalog']
            if not isinstance(catalog, dict):
                raise TypeError
            return cls(
                catalog=NavigationConfigurationCatalog.from_document(dict(catalog)),
                revision=str(document['revision']),
                created_by=str(document['created_by']),
                created_at_utc=datetime.fromisoformat(str(document['created_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration version contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationConfigurationPublication:
    revision: str
    published_by: str
    published_at_utc: datetime

    def __post_init__(self) -> None:
        revision = self.revision.strip()
        actor = self.published_by.strip()
        if not revision or not actor:
            raise NavigationConfigurationValidationError(
                'Navigation configuration publication metadata must not be empty'
            )
        if self.published_at_utc.tzinfo is None or self.published_at_utc.utcoffset() is None:
            raise NavigationConfigurationValidationError(
                'Navigation configuration publication timestamp must be timezone-aware'
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
    def from_document(
        cls,
        document: dict[str, Any],
    ) -> NavigationConfigurationPublication:
        try:
            return cls(
                revision=str(document['revision']),
                published_by=str(document['published_by']),
                published_at_utc=datetime.fromisoformat(str(document['published_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration publication contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class NavigationConfigurationSourceDocument:
    current_revision: str
    versions: tuple[NavigationConfigurationVersion, ...]
    publications: tuple[NavigationConfigurationPublication, ...]

    def __post_init__(self) -> None:
        current = self.current_revision.strip()
        version_keys = tuple(version.revision for version in self.versions)
        if not current:
            raise NavigationConfigurationValidationError(
                'Navigation configuration current revision must not be empty'
            )
        if len(version_keys) != len(set(version_keys)):
            raise NavigationConfigurationValidationError(
                'Navigation configuration versions must be unique by revision'
            )
        if current not in version_keys:
            raise NavigationConfigurationValidationError(
                'Navigation configuration current revision is missing from versions'
            )
        if not self.publications or self.publications[-1].revision != current:
            raise NavigationConfigurationValidationError(
                'Navigation configuration current publication metadata is invalid'
            )
        if any(item.revision not in version_keys for item in self.publications):
            raise NavigationConfigurationValidationError(
                'Navigation configuration publication references an unknown revision'
            )

    @classmethod
    def from_bundle(
        cls,
        bundle: NavigationConfigurationBundle,
    ) -> NavigationConfigurationSourceDocument:
        return cls(
            current_revision=bundle.revision,
            versions=(NavigationConfigurationVersion.from_bundle(bundle),),
            publications=(
                NavigationConfigurationPublication(
                    revision=bundle.revision,
                    published_by=bundle.saved_by,
                    published_at_utc=bundle.saved_at_utc,
                ),
            ),
        )

    def publish(
        self,
        bundle: NavigationConfigurationBundle,
    ) -> NavigationConfigurationSourceDocument:
        if self.current_revision == bundle.revision:
            return self
        versions = self.versions
        if bundle.revision not in {version.revision for version in versions}:
            versions = (*versions, NavigationConfigurationVersion.from_bundle(bundle))
        return NavigationConfigurationSourceDocument(
            current_revision=bundle.revision,
            versions=versions,
            publications=(
                *self.publications,
                NavigationConfigurationPublication(
                    revision=bundle.revision,
                    published_by=bundle.saved_by,
                    published_at_utc=bundle.saved_at_utc,
                ),
            ),
        )

    def current_bundle(self) -> NavigationConfigurationBundle:
        return self.require_revision(self.current_revision)

    def require_revision(self, revision: str) -> NavigationConfigurationBundle:
        normalized = revision.strip()
        versions = {version.revision: version for version in self.versions}
        try:
            version = versions[normalized]
        except KeyError as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration revision does not exist'
            ) from error
        publications = [item for item in self.publications if item.revision == normalized]
        audit = publications[-1]
        return NavigationConfigurationBundle(
            catalog=version.catalog,
            revision=version.revision,
            saved_by=audit.published_by,
            saved_at_utc=audit.published_at_utc,
        )

    def list_history(self, *, limit: int = 20) -> tuple[NavigationConfigurationBundle, ...]:
        if limit < 1:
            return ()
        result: list[NavigationConfigurationBundle] = []
        seen: set[str] = set()
        for publication in reversed(self.publications):
            if publication.revision in seen:
                continue
            seen.add(publication.revision)
            result.append(self.require_revision(publication.revision))
            if len(result) >= limit:
                break
        return tuple(result)

    def fetch_revision(self, revision: str) -> NavigationConfigurationBundle | None:
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
    def from_document(
        cls,
        document: dict[str, Any],
    ) -> NavigationConfigurationSourceDocument:
        if document.get('document_type') != SOURCE_DOCUMENT_TYPE:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source document type is invalid'
            )
        if document.get('schema_version') != SCHEMA_VERSION:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source schema version is invalid'
            )
        try:
            raw_versions = document['versions']
            raw_publications = document['publications']
            if not isinstance(raw_versions, list) or not isinstance(raw_publications, list):
                raise TypeError
            return cls(
                current_revision=str(document['current_revision']),
                versions=tuple(
                    NavigationConfigurationVersion.from_document(dict(item))
                    for item in raw_versions
                ),
                publications=tuple(
                    NavigationConfigurationPublication.from_document(dict(item))
                    for item in raw_publications
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise NavigationConfigurationValidationError(
                'Navigation configuration source contract is invalid'
            ) from error


def build_navigation_configuration_digest(catalog: NavigationConfigurationCatalog) -> str:
    canonical = json.dumps(
        catalog.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def encode_navigation_configuration_bundle(bundle: NavigationConfigurationBundle) -> bytes:
    return _encode_document(bundle.to_document())


def encode_navigation_configuration_source(source: NavigationConfigurationSourceDocument) -> bytes:
    return _encode_document(source.to_document())


def decode_navigation_configuration_source(
    payload: bytes,
) -> NavigationConfigurationSourceDocument:
    return NavigationConfigurationSourceDocument.from_document(_decode_document(payload))


def decode_navigation_configuration_import(payload: bytes) -> NavigationConfigurationBundle:
    document = _decode_document(payload)
    document_type = document.get('document_type')
    if document_type == SOURCE_DOCUMENT_TYPE:
        return NavigationConfigurationSourceDocument.from_document(document).current_bundle()
    if document_type == BUNDLE_DOCUMENT_TYPE:
        return NavigationConfigurationBundle.from_document(document)
    raise NavigationConfigurationValidationError(
        'Navigation configuration import document type is invalid'
    )


def _encode_document(document: dict[str, object]) -> bytes:
    raw = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return gzip.compress(raw, mtime=0)


def _decode_document(payload: bytes) -> dict[str, Any]:
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise NavigationConfigurationValidationError(
            'Navigation configuration compressed payload is too large'
        )
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise NavigationConfigurationValidationError(
            'Navigation configuration payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise NavigationConfigurationValidationError(
            'Navigation configuration decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NavigationConfigurationValidationError(
            'Navigation configuration payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise NavigationConfigurationValidationError(
            'Navigation configuration payload root must be an object'
        )
    return document
