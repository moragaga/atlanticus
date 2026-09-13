# Persiste una única Projection activa por SourceKey usando create-only y CAS por ETag.
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from atlanticus.connectivity.cosmos import (
    CosmosConflictError,
    CosmosError,
    CosmosItemNotFoundError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionConflictError,
    UsersConfigurationProjectionError,
    UsersConfigurationValidationError,
)
from atlanticus.web.users.configuration.models import UsersConfigurationCatalog

USERS_PROJECTION_DOCUMENT_TYPE = 'atlanticus_users_configuration_projection'
USERS_PROJECTION_SCHEMA_VERSION = 1


# El adapter usa sólo las operaciones neutrales que Atlanticus Cosmos ya expone.
class _CosmosProjectionClient(Protocol):
    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        include_metadata: bool = False,
    ) -> dict[str, Any] | None: ...

    def create_item(
        self,
        *,
        container_name: str,
        item: Mapping[str, Any],
        include_metadata: bool = False,
    ) -> dict[str, Any]: ...

    def patch_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
        operations: Sequence[CosmosPatchOperation],
        if_match_etag: str | None = None,
        include_metadata: bool = False,
    ) -> dict[str, Any]: ...


class CosmosUsersConfigurationProjectionStore(ProjectionStore[UsersConfigurationCatalog]):
    def __init__(self, *, client: _CosmosProjectionClient, container_name: str) -> None:
        normalized_container_name = container_name.strip()
        if not normalized_container_name or normalized_container_name != container_name:
            raise UsersConfigurationProjectionError(
                'Users configuration projection Cosmos container name has an invalid format'
            )
        self._client = client
        self._container_name = normalized_container_name

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[UsersConfigurationCatalog] | None:
        document = self._find_document(source_key=source_key, include_metadata=False)
        if document is None:
            return None
        projection = _projection_from_document(document)
        _require_source_key(projection=projection, source_key=source_key)
        return projection

    def replace_active(
        self,
        projection: ProjectionRecord[UsersConfigurationCatalog],
    ) -> ProjectionRecord[UsersConfigurationCatalog]:
        if not isinstance(projection.payload, UsersConfigurationCatalog):
            raise UsersConfigurationProjectionError(
                'Users configuration projection payload has an invalid type'
            )
        # Leer primero permite distinguir idempotencia de una escritura que sí requiere CAS.
        current_document = self._find_document(
            source_key=projection.source_key,
            include_metadata=True,
        )
        if current_document is None:
            return self._create_active(projection)
        current = _projection_from_document(current_document)
        _require_source_key(projection=current, source_key=projection.source_key)
        idempotent = _resolve_same_target(existing=current, candidate=projection)
        if idempotent is not None:
            return idempotent
        return self._replace_existing(
            current_document=current_document,
            projection=projection,
        )

    def _create_active(
        self,
        projection: ProjectionRecord[UsersConfigurationCatalog],
    ) -> ProjectionRecord[UsersConfigurationCatalog]:
        document = _projection_to_document(
            projection,
            item_id=_cosmos_item_id(projection.source_key),
            partition_key=projection.source_key.value,
        )
        try:
            # El primer writer crea; no se usa upsert para esconder carreras.
            saved = self._client.create_item(
                container_name=self._container_name,
                item=document,
                include_metadata=True,
            )
        except CosmosConflictError as error:
            # Otro writer ganó el create. Sólo es éxito si materializó exactamente el mismo target.
            concurrent_document = self._find_document(
                source_key=projection.source_key,
                include_metadata=True,
            )
            if concurrent_document is None:
                raise UsersConfigurationProjectionError(
                    'Users configuration projection disappeared after create conflict'
                ) from error
            return _resolve_concurrent_projection(
                document=concurrent_document,
                candidate=projection,
                error=error,
            )
        except CosmosError as error:
            raise UsersConfigurationProjectionError(
                'Could not create Cosmos users configuration projection'
            ) from error
        return _require_persisted_projection(saved=saved, candidate=projection)

    def _replace_existing(
        self,
        *,
        current_document: Mapping[str, Any],
        projection: ProjectionRecord[UsersConfigurationCatalog],
    ) -> ProjectionRecord[UsersConfigurationCatalog]:
        item_id = _cosmos_item_id(projection.source_key)
        etag = _required_etag(current_document)
        desired = _projection_to_document(projection)
        # id y partition_key son estables; sólo se reemplaza el contenido lógico de Projection.
        operations = tuple(
            CosmosPatchOperation(operation='set', path=f'/{field}', value=value)
            for field, value in desired.items()
        )
        try:
            saved = self._client.patch_item(
                container_name=self._container_name,
                item_id=item_id,
                partition_key=projection.source_key.value,
                operations=operations,
                if_match_etag=etag,
                include_metadata=True,
            )
        except CosmosPreconditionFailedError as error:
            # Releer después del 412 permite reconocer un retry idempotente sin last-write-wins.
            concurrent_document = self._find_document(
                source_key=projection.source_key,
                include_metadata=True,
            )
            if concurrent_document is None:
                raise UsersConfigurationProjectionError(
                    'Users configuration projection disappeared during concurrent update'
                ) from error
            return _resolve_concurrent_projection(
                document=concurrent_document,
                candidate=projection,
                error=error,
            )
        except CosmosItemNotFoundError as error:
            raise UsersConfigurationProjectionError(
                'Users configuration projection disappeared during update'
            ) from error
        except CosmosError as error:
            raise UsersConfigurationProjectionError(
                'Could not update Cosmos users configuration projection'
            ) from error
        return _require_persisted_projection(saved=saved, candidate=projection)

    def _find_document(
        self,
        *,
        source_key: SourceKey,
        include_metadata: bool,
    ) -> dict[str, Any] | None:
        try:
            return self._client.find_item(
                container_name=self._container_name,
                item_id=_cosmos_item_id(source_key),
                partition_key=source_key.value,
                include_metadata=include_metadata,
            )
        except CosmosError as error:
            raise UsersConfigurationProjectionError(
                'Could not read Cosmos users configuration projection'
            ) from error


# La forma durable conserva sólo provenance canónica de Projection y el payload Users.
def _projection_to_document(
    projection: ProjectionRecord[UsersConfigurationCatalog],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        'document_type': USERS_PROJECTION_DOCUMENT_TYPE,
        'schema_version': USERS_PROJECTION_SCHEMA_VERSION,
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
    document: Mapping[str, Any],
) -> ProjectionRecord[UsersConfigurationCatalog]:
    if document.get('document_type') != USERS_PROJECTION_DOCUMENT_TYPE:
        raise UsersConfigurationProjectionError(
            'Users configuration projection document type is invalid'
        )
    if document.get('schema_version') != USERS_PROJECTION_SCHEMA_VERSION:
        raise UsersConfigurationProjectionError(
            'Users configuration projection schema version is invalid'
        )
    try:
        payload = document['payload']
        if not isinstance(payload, Mapping):
            raise TypeError
        return ProjectionRecord(
            source_key=SourceKey(str(document['source_key'])),
            source_release_id=SourceReleaseId(str(document['source_release_id'])),
            source_published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
            projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            payload=UsersConfigurationCatalog.from_document(dict(payload)),
        )
    except (KeyError, TypeError, ValueError, UsersConfigurationValidationError) as error:
        raise UsersConfigurationProjectionError(
            'Users configuration projection contract is invalid'
        ) from error


# Una exact release sólo puede producir un payload lógico; el retry conserva projected_at original.
def _resolve_same_target(
    *,
    existing: ProjectionRecord[UsersConfigurationCatalog],
    candidate: ProjectionRecord[UsersConfigurationCatalog],
) -> ProjectionRecord[UsersConfigurationCatalog] | None:
    if existing.source_release_id == candidate.source_release_id:
        if existing.source_release != candidate.source_release:
            raise UsersConfigurationProjectionError(
                'Users configuration projection release metadata is inconsistent'
            )
        if existing.payload != candidate.payload:
            raise UsersConfigurationProjectionError(
                'Users configuration projection release produced a different payload'
            )
        return existing
    return None


# Un conflicto CAS sólo se reconcilia como éxito cuando el ganador dejó exactamente el mismo target.
def _resolve_concurrent_projection(
    *,
    document: Mapping[str, Any],
    candidate: ProjectionRecord[UsersConfigurationCatalog],
    error: CosmosError,
) -> ProjectionRecord[UsersConfigurationCatalog]:
    concurrent = _projection_from_document(document)
    _require_source_key(projection=concurrent, source_key=candidate.source_key)
    idempotent = _resolve_same_target(existing=concurrent, candidate=candidate)
    if idempotent is not None:
        return idempotent
    raise UsersConfigurationProjectionConflictError(
        'Users configuration projection changed concurrently'
    ) from error


def _require_persisted_projection(
    *,
    saved: Mapping[str, Any],
    candidate: ProjectionRecord[UsersConfigurationCatalog],
) -> ProjectionRecord[UsersConfigurationCatalog]:
    persisted = _projection_from_document(saved)
    if persisted != candidate:
        raise UsersConfigurationProjectionError(
            'Cosmos persisted a different users configuration projection'
        )
    return persisted


def _require_source_key(
    *,
    projection: ProjectionRecord[UsersConfigurationCatalog],
    source_key: SourceKey,
) -> None:
    if projection.source_key != source_key:
        raise UsersConfigurationProjectionError(
            'Users configuration projection source key does not match request'
        )


def _required_etag(document: Mapping[str, Any]) -> str:
    value = document.get('_etag')
    if not isinstance(value, str) or not value.strip():
        raise UsersConfigurationProjectionError(
            'Users configuration projection document is missing ETag'
        )
    return value


# Un hash estable evita restricciones de caracteres/tamaño de Cosmos sin cambiar
# la partición lógica.
def _cosmos_item_id(source_key: SourceKey) -> str:
    digest = hashlib.sha256(source_key.value.encode('utf-8')).hexdigest()
    return f'users-configuration-projection-{digest}'
