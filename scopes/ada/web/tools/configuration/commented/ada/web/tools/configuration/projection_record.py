# Serializa la Tool Projection activa sin inventar identidad adicional.
# Conserva Source release exacta y ProjectionTarget.dependencies para persistencia local/Cosmos.

from __future__ import annotations

from datetime import datetime
from typing import Any

from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.models import ToolConfiguration
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

TOOL_PROJECTION_DOCUMENT_TYPE = 'ada_tool_projection_record'
TOOL_PROJECTION_SCHEMA_VERSION = 1


def tool_projection_to_document(
    projection: ProjectionRecord[ToolConfiguration],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    # Sólo el payload ToolConfiguration pertenece a este codec.
    if not isinstance(projection.payload, ToolConfiguration):
        raise ToolConfigurationProjectionError(
            'Tool projection payload must be ToolConfiguration'
        )
    document: dict[str, object] = {
        'document_type': TOOL_PROJECTION_DOCUMENT_TYPE,
        'schema_version': TOOL_PROJECTION_SCHEMA_VERSION,
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
    # id/partition_key son metadata del provider y no modifican ProjectionRecord.
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


def tool_projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[ToolConfiguration]:
    if document.get('document_type') != TOOL_PROJECTION_DOCUMENT_TYPE:
        raise ToolConfigurationProjectionError(
            'Tool projection document type is invalid'
        )
    if document.get('schema_version') != TOOL_PROJECTION_SCHEMA_VERSION:
        raise ToolConfigurationProjectionError(
            'Tool projection schema version is invalid'
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
        # La reconstrucción conserva la provenance exacta y no crea revision strings privadas.
        return ProjectionRecord(
            source_key=SourceKey(str(document['source_key'])),
            source_release_id=SourceReleaseId(str(document['source_release_id'])),
            source_published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
            projected_at_utc=datetime.fromisoformat(
                str(document['projected_at_utc'])
            ),
            payload=ToolConfiguration.from_document(payload),
            dependencies=tuple(
                _projection_target_from_document(item)
                for item in dependencies
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ToolConfigurationProjectionError(
            'Tool projection contract is invalid'
        ) from error


def _projection_target_to_document(
    target: ProjectionTarget,
) -> dict[str, object]:
    return {
        'source_key': target.source_key.value,
        'source_release_id': target.source_release_id.value,
        'source_published_at_utc': (
            target.source_release.published_at_utc.isoformat()
        ),
        'dependencies': [
            _projection_target_to_document(dependency)
            for dependency in target.dependencies
        ],
    }


def _projection_target_from_document(
    document: dict[str, Any],
) -> ProjectionTarget:
    dependencies = document['dependencies']
    if not isinstance(dependencies, list) or not all(
        isinstance(item, dict) for item in dependencies
    ):
        raise TypeError
    return ProjectionTarget(
        source_key=SourceKey(str(document['source_key'])),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(
                str(document['source_release_id'])
            ),
            published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
        ),
        dependencies=tuple(
            _projection_target_from_document(item)
            for item in dependencies
        ),
    )
