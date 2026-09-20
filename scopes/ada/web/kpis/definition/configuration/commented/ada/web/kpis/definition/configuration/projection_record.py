# Codec durable de ProjectionRecord[KpiDefinitionCatalog].
from __future__ import annotations

from datetime import datetime
from typing import Any

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.configuration.errors import KpiDefinitionProjectionError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE = 'ada_kpi_definition_projection_record'
KPI_DEFINITION_PROJECTION_SCHEMA_VERSION = 1


def kpi_definition_projection_to_document(
    projection: ProjectionRecord[KpiDefinitionCatalog],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    if not isinstance(projection.payload, KpiDefinitionCatalog):
        raise KpiDefinitionProjectionError(
            'KPI Definition projection payload must be KpiDefinitionCatalog'
        )
    document: dict[str, object] = {
        'document_type': KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE,
        'schema_version': KPI_DEFINITION_PROJECTION_SCHEMA_VERSION,
        'source_key': projection.source_key.value,
        'source_release_id': projection.source_release_id.value,
        'source_published_at_utc': projection.source_published_at_utc.isoformat(),
        'projected_at_utc': projection.projected_at_utc.isoformat(),
        'dependencies': [
            _projection_target_to_document(dependency) for dependency in projection.dependencies
        ],
        'payload': projection.payload.to_document(),
    }
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


def kpi_definition_projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[KpiDefinitionCatalog]:
    if document.get('document_type') != KPI_DEFINITION_PROJECTION_DOCUMENT_TYPE:
        raise KpiDefinitionProjectionError('KPI Definition projection document type is invalid')
    if document.get('schema_version') != KPI_DEFINITION_PROJECTION_SCHEMA_VERSION:
        raise KpiDefinitionProjectionError('KPI Definition projection schema version is invalid')
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
            payload=KpiDefinitionCatalog.from_document(payload),
            dependencies=tuple(_projection_target_from_document(item) for item in dependencies),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise KpiDefinitionProjectionError('KPI Definition projection contract is invalid') from error


def _projection_target_to_document(target: ProjectionTarget) -> dict[str, object]:
    return {
        'source_key': target.source_key.value,
        'source_release_id': target.source_release_id.value,
        'source_published_at_utc': target.source_release.published_at_utc.isoformat(),
        'dependencies': [
            _projection_target_to_document(dependency) for dependency in target.dependencies
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
            published_at_utc=datetime.fromisoformat(str(document['source_published_at_utc'])),
        ),
        dependencies=tuple(_projection_target_from_document(item) for item in dependencies),
    )
