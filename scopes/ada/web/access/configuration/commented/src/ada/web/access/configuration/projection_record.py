# La Projection durable conserva payload y provenance exacta, incluidas dependencies recursivas.
# Schema 2 corresponde al payload con catálogo explícito de access_keys.

from __future__ import annotations

from datetime import datetime
from typing import Any

from ada.web.access.configuration.errors import AdaAccessConfigurationProjectionError
from ada.web.access.configuration.models import AdaAccessConfiguration
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

ADA_ACCESS_PROJECTION_DOCUMENT_TYPE = 'ada_access_projection_record'
ADA_ACCESS_PROJECTION_SCHEMA_VERSION = 2


def ada_access_projection_to_document(
    projection: ProjectionRecord[AdaAccessConfiguration],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    if not isinstance(projection.payload, AdaAccessConfiguration):
        raise AdaAccessConfigurationProjectionError(
            'ADA access projection payload must be AdaAccessConfiguration'
        )
    document: dict[str, object] = {
        'document_type': ADA_ACCESS_PROJECTION_DOCUMENT_TYPE,
        'schema_version': ADA_ACCESS_PROJECTION_SCHEMA_VERSION,
        'source_key': projection.source_key.value,
        'source_release_id': projection.source_release_id.value,
        'source_published_at_utc': projection.source_published_at_utc.isoformat(),
        'projected_at_utc': projection.projected_at_utc.isoformat(),
        'dependencies': [
            _projection_target_to_document(dependency)
            for dependency in projection.dependencies
        ],
        'payload': projection.payload.to_document(),
    }
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


def ada_access_projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[AdaAccessConfiguration]:
    if document.get('document_type') != ADA_ACCESS_PROJECTION_DOCUMENT_TYPE:
        raise AdaAccessConfigurationProjectionError(
            'ADA access projection document type is invalid'
        )
    if document.get('schema_version') != ADA_ACCESS_PROJECTION_SCHEMA_VERSION:
        raise AdaAccessConfigurationProjectionError(
            'ADA access projection schema version is invalid'
        )
    try:
        payload = document['payload']
        dependencies = document['dependencies']
        if not isinstance(payload, dict):
            raise TypeError
        if not isinstance(dependencies, list) or not all(
            isinstance(item, dict) for item in dependencies
        ):
            raise TypeError
        return ProjectionRecord(
            source_key=SourceKey(str(document['source_key'])),
            source_release_id=SourceReleaseId(str(document['source_release_id'])),
            source_published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
            projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            payload=AdaAccessConfiguration.from_document(dict(payload)),
            dependencies=tuple(
                _projection_target_from_document(item) for item in dependencies
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AdaAccessConfigurationProjectionError(
            'ADA access projection contract is invalid'
        ) from error


def _projection_target_to_document(target: ProjectionTarget) -> dict[str, object]:
    return {
        'source_key': target.source_key.value,
        'source_release_id': target.source_release_id.value,
        'source_published_at_utc': target.source_release.published_at_utc.isoformat(),
        'dependencies': [
            _projection_target_to_document(dependency)
            for dependency in target.dependencies
        ],
    }


def _projection_target_from_document(document: dict[str, Any]) -> ProjectionTarget:
    dependencies = document['dependencies']
    if not isinstance(dependencies, list) or not all(
        isinstance(item, dict) for item in dependencies
    ):
        raise TypeError
    return ProjectionTarget(
        source_key=SourceKey(str(document['source_key'])),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(str(document['source_release_id'])),
            published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
        ),
        dependencies=tuple(
            _projection_target_from_document(item) for item in dependencies
        ),
    )
