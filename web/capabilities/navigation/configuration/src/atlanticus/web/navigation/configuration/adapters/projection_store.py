from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol

from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationValidationError,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId

NAVIGATION_PROJECTION_DOCUMENT_TYPE = 'atlanticus_navigation_projection_record'
NAVIGATION_PROJECTION_SCHEMA_VERSION = 1


class CosmosProjectionClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None: ...

    def upsert_item(
        self,
        *,
        container_name: str,
        item: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class LocalNavigationProjectionStoreSettings:
    root: Path


class LocalNavigationProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    def __init__(self, settings: LocalNavigationProjectionStoreSettings) -> None:
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        path = self._path(source_key)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(document, dict):
                raise TypeError
            projection = _projection_from_document(document)
        except NavigationConfigurationProjectionError:
            raise
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Local navigation projection is invalid'
            ) from error
        if projection.source_key != source_key:
            raise NavigationConfigurationProjectionError(
                'Local navigation projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        try:
            payload = json.dumps(
                _projection_to_document(projection),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
            _atomic_write_bytes(self._path(projection.source_key), payload)
        except NavigationConfigurationProjectionError:
            raise
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not write local navigation projection'
            ) from error
        return projection

    def _path(self, source_key: SourceKey) -> Path:
        digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
        return self._settings.root / f'navigation_projection_{digest}.json'


@dataclass(frozen=True, slots=True)
class CosmosNavigationProjectionStoreSettings:
    container_name: str

    def __post_init__(self) -> None:
        container_name = self.container_name.strip()
        if not container_name:
            raise ValueError('Cosmos navigation projection container must not be empty')
        object.__setattr__(self, 'container_name', container_name)


class CosmosNavigationProjectionStore(ProjectionStore[NavigationConfigurationCatalog]):
    def __init__(
        self,
        *,
        client: CosmosProjectionClient,
        settings: CosmosNavigationProjectionStoreSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[NavigationConfigurationCatalog] | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
            )
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not read Cosmos navigation projection'
            ) from error
        if document is None:
            return None
        projection = _projection_from_document(document)
        if projection.source_key != source_key:
            raise NavigationConfigurationProjectionError(
                'Cosmos navigation projection source key does not match request'
            )
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[NavigationConfigurationCatalog],
    ) -> ProjectionRecord[NavigationConfigurationCatalog]:
        document = _projection_to_document(
            projection,
            item_id=_cosmos_item_id(projection.source_key),
            partition_key=projection.source_key.value,
        )
        try:
            saved = self._client.upsert_item(
                container_name=self._settings.container_name,
                item=document,
            )
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not write Cosmos navigation projection'
            ) from error
        persisted = _projection_from_document(saved)
        if persisted.source_key != projection.source_key:
            raise NavigationConfigurationProjectionError(
                'Cosmos navigation projection persisted a different source key'
            )
        return persisted


def _projection_to_document(
    projection: ProjectionRecord[NavigationConfigurationCatalog],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        'document_type': NAVIGATION_PROJECTION_DOCUMENT_TYPE,
        'schema_version': NAVIGATION_PROJECTION_SCHEMA_VERSION,
        'source_key': projection.source_key.value,
        'source_release_id': projection.source_release_id.value,
        'source_published_at_utc': projection.source_published_at_utc.isoformat(),
        'projected_at_utc': projection.projected_at_utc.isoformat(),
        'payload': projection.payload.to_document(),
    }
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


def _projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[NavigationConfigurationCatalog]:
    if document.get('document_type') != NAVIGATION_PROJECTION_DOCUMENT_TYPE:
        raise NavigationConfigurationProjectionError(
            'Navigation projection document type is invalid'
        )
    if document.get('schema_version') != NAVIGATION_PROJECTION_SCHEMA_VERSION:
        raise NavigationConfigurationProjectionError(
            'Navigation projection schema version is invalid'
        )
    try:
        payload = document['payload']
        if not isinstance(payload, dict):
            raise TypeError
        return ProjectionRecord(
            source_key=SourceKey(str(document['source_key'])),
            source_release_id=SourceReleaseId(str(document['source_release_id'])),
            source_published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
            projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            payload=NavigationConfigurationCatalog.from_document(dict(payload)),
        )
    except (KeyError, TypeError, ValueError, NavigationConfigurationValidationError) as error:
        raise NavigationConfigurationProjectionError(
            'Navigation projection contract is invalid'
        ) from error


def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'navigation-projection-{digest}'


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
