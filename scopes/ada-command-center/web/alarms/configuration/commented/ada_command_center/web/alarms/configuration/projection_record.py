# Espejo pedagógico en español; el comportamiento equivale al archivo de src.
from __future__ import annotations

from datetime import datetime
from typing import Any

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE = (
    'ada_command_center_alarm_configuration_projection_record'
)
ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION = 1


# El codec representa una proyección genérica con la evidencia Tool congelada dentro del payload; nunca reconsulta el catálogo.
def alarm_configuration_projection_to_document(
    projection: ProjectionRecord[AlarmConfigurationSnapshot],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    if not isinstance(projection.payload, AlarmConfigurationSnapshot):
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection payload must be AlarmConfigurationSnapshot'
        )
    document: dict[str, object] = {
        'document_type': ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
        'schema_version': ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
        'source_key': projection.source_key.value,
        'source_release_id': projection.source_release_id.value,
        'source_published_at_utc': projection.source_published_at_utc.isoformat(),
        'projected_at_utc': projection.projected_at_utc.isoformat(),
        'dependencies': [
            _target_to_document(dependency) for dependency in projection.dependencies
        ],
        'payload': projection.payload.to_document(),
    }
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


# Restauramos identidad y fechas exactas de Source; un esquema inválido no debe parecer ausencia de proyección.
def alarm_configuration_projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[AlarmConfigurationSnapshot]:
    if not isinstance(document, dict):
        raise AlarmConfigurationProjectionError('Alarm Configuration projection must be an object')
    if document.get('document_type') != ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE:
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection document type is invalid'
        )
    if document.get('schema_version') != ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION:
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection schema version is invalid'
        )
    try:
        payload = document['payload']
        dependencies = document['dependencies']
        if not isinstance(payload, dict) or not isinstance(dependencies, list):
            raise TypeError
        if any(not isinstance(item, dict) for item in dependencies):
            raise TypeError
        return ProjectionRecord(
            source_key=SourceKey(_text(document, 'source_key')),
            source_release_id=SourceReleaseId(_text(document, 'source_release_id')),
            source_published_at_utc=datetime.fromisoformat(
                _text(document, 'source_published_at_utc')
            ),
            projected_at_utc=datetime.fromisoformat(_text(document, 'projected_at_utc')),
            payload=AlarmConfigurationSnapshot.from_document(payload),
            dependencies=tuple(_target_from_document(item) for item in dependencies),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection contract is invalid'
        ) from error


# Se conserva la forma genérica de dependencias por compatibilidad con ProjectionRecord; el flujo Alarm no declara dependencias Tool aquí.
def _target_to_document(target: ProjectionTarget) -> dict[str, object]:
    return {
        'source_key': target.source_key.value,
        'source_release_id': target.source_release_id.value,
        'source_published_at_utc': target.source_release.published_at_utc.isoformat(),
        'dependencies': [_target_to_document(item) for item in target.dependencies],
    }


def _target_from_document(document: dict[str, Any]) -> ProjectionTarget:
    dependencies = document['dependencies']
    if not isinstance(dependencies, list) or any(
        not isinstance(item, dict) for item in dependencies
    ):
        raise TypeError
    return ProjectionTarget(
        source_key=SourceKey(_text(document, 'source_key')),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(_text(document, 'source_release_id')),
            published_at_utc=datetime.fromisoformat(_text(document, 'source_published_at_utc')),
        ),
        dependencies=tuple(_target_from_document(item) for item in dependencies),
    )


def _text(document: dict[str, Any], field_name: str) -> str:
    value = document[field_name]
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    return value
