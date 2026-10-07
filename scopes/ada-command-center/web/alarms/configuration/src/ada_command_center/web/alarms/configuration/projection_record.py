from __future__ import annotations

from ada.contracts.alarms import (
    ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE as _ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
    ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION as _ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
    AlarmConfigurationProjection,
    AlarmConfigurationProjectionDependency,
    AlarmConfigurationProjectionValidationError,
    AlarmConfigurationSnapshot,
)
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE = _ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE
ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION = _ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION


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
    try:
        contract = AlarmConfigurationProjection(
            source_key=projection.source_key.value,
            source_release_id=projection.source_release_id.value,
            source_published_at_utc=projection.source_published_at_utc,
            projected_at_utc=projection.projected_at_utc,
            snapshot=projection.payload,
            dependencies=tuple(_dependency_from_target(item) for item in projection.dependencies),
        )
        return contract.to_document(item_id=item_id, partition_key=partition_key)
    except (TypeError, ValueError) as error:
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection contract is invalid'
        ) from error


def alarm_configuration_projection_from_document(
    document: dict[str, object],
) -> ProjectionRecord[AlarmConfigurationSnapshot]:
    try:
        contract = AlarmConfigurationProjection.from_document(document)
        return ProjectionRecord(
            source_key=SourceKey(contract.source_key),
            source_release_id=SourceReleaseId(contract.source_release_id),
            source_published_at_utc=contract.source_published_at_utc,
            projected_at_utc=contract.projected_at_utc,
            payload=contract.snapshot,
            dependencies=tuple(_target_from_dependency(item) for item in contract.dependencies),
        )
    except AlarmConfigurationProjectionValidationError as error:
        raise AlarmConfigurationProjectionError(str(error)) from error
    except (TypeError, ValueError) as error:
        raise AlarmConfigurationProjectionError(
            'Alarm Configuration projection contract is invalid'
        ) from error


def _dependency_from_target(target: ProjectionTarget) -> AlarmConfigurationProjectionDependency:
    return AlarmConfigurationProjectionDependency(
        source_key=target.source_key.value,
        source_release_id=target.source_release_id.value,
        source_published_at_utc=target.source_release.published_at_utc,
        dependencies=tuple(_dependency_from_target(item) for item in target.dependencies),
    )


def _target_from_dependency(dependency: AlarmConfigurationProjectionDependency) -> ProjectionTarget:
    return ProjectionTarget(
        source_key=SourceKey(dependency.source_key),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId(dependency.source_release_id),
            published_at_utc=dependency.source_published_at_utc,
        ),
        dependencies=tuple(_target_from_dependency(item) for item in dependency.dependencies),
    )
