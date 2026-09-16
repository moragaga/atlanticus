# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
from __future__ import annotations

from datetime import datetime
from typing import Any

from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationValidationError,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId

NAVIGATION_PROJECTION_DOCUMENT_TYPE = 'atlanticus_navigation_projection_record'
NAVIGATION_PROJECTION_SCHEMA_VERSION = 1


# Operación: navigation_projection_to_document mantiene la misma semántica que el código productivo.
def navigation_projection_to_document(
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


# Operación: navigation_projection_from_document mantiene la misma semántica que el código productivo.
def navigation_projection_from_document(
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
