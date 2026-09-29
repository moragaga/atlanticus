# La proyección valida releases, identidad y forma del documento antes de escribir datos de consumo.
from __future__ import annotations

from datetime import datetime
from typing import Any

from ada.web.operational.identification.errors import OperationalIdentificationError
from ada.web.operational.identification.keys import source_kind
from ada.web.operational.identification.models import (
    OperationalAssignment,
    OperationalCatalog,
    OperationalDocument,
    parse_document,
)
from ada.web.operational.identification.source import OperationalSourceCodec
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.projection.service import ProjectionBuilder, SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import (
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceResource,
)
from atlanticus.web.source.store import SourceStore

_CATALOG_TYPE = 'ada_operational_catalog_projection'
_ASSIGNMENT_TYPE = 'ada_operational_assignment_projection'


# Se comprueba que el payload corresponda a la identidad descrita por la SourceKey.
class OperationalProjectionBuilder(ProjectionBuilder[OperationalDocument]):
    def __init__(self, codec: OperationalSourceCodec | None = None) -> None:
        self._codec = codec or OperationalSourceCodec()

    def build(
        self,
        *,
        target: ProjectionTarget,
        release: SourceReleaseMetadata,
        resources: tuple[SourceResource, ...],
    ) -> OperationalDocument:
        if target.source_key != release.source_key or target.source_release != release.release_ref:
            raise OperationalIdentificationError(
                'Operational projection target differs from release'
            )
        kind, user_id = source_kind(target.source_key)
        value = self._codec.decode(resources)
        if (kind == 'catalog' and not isinstance(value, OperationalCatalog)) or (
            kind == 'assignment'
            and (not isinstance(value, OperationalAssignment) or value.user_id != user_id)
        ):
            raise OperationalIdentificationError(
                'Operational projection payload differs from source'
            )
        return value


# Se reutiliza SourceProjectionService existente; no se implementa otro orquestador.
def create_operational_projection_service(
    *,
    source: SourceStore,
    projection: ProjectionStore[OperationalDocument],
) -> SourceProjectionService[OperationalDocument]:
    return SourceProjectionService(
        source=source,
        projection=projection,
        builder=OperationalProjectionBuilder(),
    )


# Los atributos se exponen inline dentro del documento de Cosmos para lectura puntual.
def projection_to_document(
    record: ProjectionRecord[OperationalDocument],
    *,
    item_id: str,
) -> dict[str, object]:
    kind, user_id = source_kind(record.source_key)
    if record.dependencies:
        raise OperationalIdentificationError('Operational projections cannot add dependencies')
    if kind == 'catalog' and not isinstance(record.payload, OperationalCatalog):
        raise OperationalIdentificationError('Operational catalog projection payload is invalid')
    if kind == 'assignment' and (
        not isinstance(record.payload, OperationalAssignment) or record.payload.user_id != user_id
    ):
        raise OperationalIdentificationError('Operational assignment projection payload is invalid')
    return {
        'id': item_id,
        'partition_key': record.source_key.value,
        'document_type': _CATALOG_TYPE if kind == 'catalog' else _ASSIGNMENT_TYPE,
        'schema_version': 1,
        'source_key': record.source_key.value,
        'source_release_id': record.source_release_id.value,
        'source_published_at_utc': record.source_published_at_utc.isoformat(),
        'projected_at_utc': record.projected_at_utc.isoformat(),
        **record.payload.to_document(),
    }


# Se rechazan documentos cuyo tipo, identidad o clave de partición no coincidan.
def projection_from_document(document: dict[str, Any]) -> ProjectionRecord[OperationalDocument]:
    if not isinstance(document, dict):
        raise OperationalIdentificationError('Operational projection must be a document')
    try:
        source_key = SourceKey(document['source_key'])
        kind, user_id = source_kind(source_key)
        expected_type = _CATALOG_TYPE if kind == 'catalog' else _ASSIGNMENT_TYPE
        if document['document_type'] != expected_type or document['schema_version'] != 1:
            raise OperationalIdentificationError('Operational projection type is invalid')
        payload_keys = (
            ('areas', 'groups', 'positions')
            if kind == 'catalog'
            else ('user_id', 'area_id', 'position_id', 'group_id')
        )
        payload = parse_document(kind, {key: document[key] for key in payload_keys})
        if kind == 'assignment' and payload.user_id != user_id:
            raise OperationalIdentificationError('Operational projection user identity is invalid')
        if document['partition_key'] != source_key.value:
            raise OperationalIdentificationError('Operational projection partition is invalid')
        return ProjectionRecord(
            source_key=source_key,
            source_release_id=SourceReleaseId(document['source_release_id']),
            source_published_at_utc=datetime.fromisoformat(document['source_published_at_utc']),
            projected_at_utc=datetime.fromisoformat(document['projected_at_utc']),
            payload=payload,
        )
    except (KeyError, ValueError, TypeError) as error:
        raise OperationalIdentificationError(
            'Operational projection document is invalid'
        ) from error
