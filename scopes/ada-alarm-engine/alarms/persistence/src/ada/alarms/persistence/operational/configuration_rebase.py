from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ada.alarms.core import commit_id_for, cycle_id_for
from ada.alarms.persistence.operational.configuration_adoption import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    GroupCommitReference,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import (
    restore_group_lifecycle,
    snapshot_group_lifecycle,
)
from ada.alarms.persistence.operational.models import (
    GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
)
from ada.alarms.persistence.operational.technical_incidents import snapshot_technical_incidents

CONFIGURATION_REBASE_SCHEMA_VERSION = 'group-configuration-rebase.v1'


@dataclass(frozen=True, slots=True)
class PreparedConfigurationRebase:
    adoption: ConfigurationAdoptionRecord
    group_records: tuple[EngineCommitRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adoption, ConfigurationAdoptionRecord):
            raise TypeError('adoption must be ConfigurationAdoptionRecord')
        if not isinstance(self.group_records, tuple) or not all(
            isinstance(record, EngineCommitRecord) for record in self.group_records
        ):
            raise TypeError('group_records must contain EngineCommitRecord values')
        if bool(self.group_records) != isinstance(self.adoption, ConfigurationAdoptionRecordV2):
            raise ValueError('V2 adoption requires group rebases; V1 requires none')


def prepare_configuration_rebase(
    *,
    previous_snapshot: GroupRuntimeSnapshot,
    source_ref: AlarmArtifactRefSnapshot,
    target_ref: AlarmArtifactRefSnapshot,
    cycle_at: datetime,
    committed_at: datetime,
    runtime_artifact_version: str,
) -> EngineCommitRecord:
    if not isinstance(previous_snapshot, GroupRuntimeSnapshot):
        raise TypeError('previous_snapshot must be GroupRuntimeSnapshot')
    _validate_refs(source_ref, target_ref)
    _validate_times(cycle_at, committed_at)
    if not isinstance(runtime_artifact_version, str) or not runtime_artifact_version.strip():
        raise ValueError('runtime_artifact_version must be non-empty')
    before = previous_snapshot.as_document()
    if before['snapshot_schema_version'] != GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION:
        raise ValueError('configuration rebase requires recoverable snapshot v3')
    old_basis = _basis(source_ref)
    new_basis = _basis(target_ref)
    if before['state_basis'] != old_basis:
        raise ValueError('previous snapshot basis differs from source EFFECTIVE artifact')
    group_state = restore_group_lifecycle(previous_snapshot)
    incidents = snapshot_technical_incidents(previous_snapshot)
    group = group_state.priority_group
    cycle_id = cycle_id_for(cycle_at)
    commit_id = commit_id_for(cycle_id, group)
    metadata = EngineCommitMetadata(
        commit_id=commit_id,
        cycle_id=cycle_id,
        priority_group=group,
        previous_commit_id=previous_snapshot.last_commit_id,
        evaluated_at=_ts(cycle_at),
        committed_at=_ts(committed_at),
        alarm_configuration_revision=target_ref.alarm_configuration_revision,
        tool_registry_revision=target_ref.confirmed_tool_catalog_revision,
        runtime_artifact_version=runtime_artifact_version,
        affected_alarms=tuple(
            sorted(
                {
                    *(alarm.alarm_identity.canonical_key for alarm in group_state.alarms),
                    *(incident.alarm_identity.canonical_key for incident in incidents),
                }
            )
        ),
    )
    snapshot = snapshot_group_lifecycle(
        group_state,
        commit_id=commit_id,
        alarm_configuration_revision=target_ref.alarm_configuration_revision,
        tool_registry_revision=target_ref.confirmed_tool_catalog_revision,
        technical_incidents=incidents,
    )
    return EngineCommitRecord.create(
        commit=metadata,
        snapshot_after=snapshot,
        records={
            'configuration_rebases': [
                {
                    'schema_version': CONFIGURATION_REBASE_SCHEMA_VERSION,
                    'priority_group': group,
                    'previous_basis': old_basis,
                    'target_basis': new_basis,
                }
            ],
        },
    )


def prepare_noop_configuration_adoption(
    *,
    snapshots: Sequence[GroupRuntimeSnapshot],
    source_ref: AlarmArtifactRefSnapshot | None,
    target_ref: AlarmArtifactRefSnapshot,
    adoption_id: str,
    cycle_at: datetime,
    committed_at: datetime,
    runtime_artifact_version: str,
) -> PreparedConfigurationRebase:
    if source_ref is None:
        if snapshots:
            raise ValueError('bootstrap cannot rebase preexisting group snapshots')
        if not isinstance(target_ref, AlarmArtifactRefSnapshot):
            raise TypeError('target_ref must be AlarmArtifactRefSnapshot')
    else:
        _validate_refs(source_ref, target_ref)
    _validate_times(cycle_at, committed_at)
    if isinstance(snapshots, str | bytes) or not isinstance(snapshots, Sequence):
        raise TypeError('snapshots must be a sequence')
    if any(not isinstance(snapshot, GroupRuntimeSnapshot) for snapshot in snapshots):
        raise TypeError('snapshots must contain GroupRuntimeSnapshot values')
    groups = [snapshot.priority_group for snapshot in snapshots]
    if len(set(groups)) != len(groups):
        raise ValueError('configuration adoption snapshots must be unique by group')
    if source_ref is None or not snapshots:
        adoption = ConfigurationAdoptionRecord.create(
            adoption_id=adoption_id,
            previous_artifact_ref=source_ref,
            target_artifact_ref=target_ref,
            effective_at=_ts(cycle_at),
            committed_at=_ts(committed_at),
        )
        return PreparedConfigurationRebase(adoption=adoption, group_records=())
    records = tuple(
        prepare_configuration_rebase(
            previous_snapshot=snapshot,
            source_ref=source_ref,
            target_ref=target_ref,
            cycle_at=cycle_at,
            committed_at=committed_at,
            runtime_artifact_version=runtime_artifact_version,
        )
        for snapshot in sorted(snapshots, key=lambda item: item.priority_group)
    )
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id=adoption_id,
        previous_artifact_ref=source_ref,
        target_artifact_ref=target_ref,
        effective_at=_ts(cycle_at),
        committed_at=_ts(committed_at),
        group_commits=tuple(
            GroupCommitReference(
                priority_group=record.commit.priority_group,
                commit_id=record.commit.commit_id,
                record_hash=record.record_hash,
            )
            for record in records
        ),
    )
    return PreparedConfigurationRebase(adoption=adoption, group_records=records)


def _validate_refs(source: AlarmArtifactRefSnapshot, target: AlarmArtifactRefSnapshot) -> None:
    if not isinstance(source, AlarmArtifactRefSnapshot) or not isinstance(
        target, AlarmArtifactRefSnapshot
    ):
        raise TypeError('source_ref and target_ref must be AlarmArtifactRefSnapshot')
    if source.source_key != target.source_key:
        raise ValueError('adoption cannot change artifact source_key')
    if source.result_id == target.result_id:
        raise ValueError('adoption must change materialization result_id')


def _basis(reference: AlarmArtifactRefSnapshot) -> dict[str, str]:
    return {
        'alarm_configuration_revision': reference.alarm_configuration_revision,
        'tool_registry_revision': reference.confirmed_tool_catalog_revision,
    }


def _validate_times(cycle_at: datetime, committed_at: datetime) -> None:
    for name, value in (('cycle_at', cycle_at), ('committed_at', committed_at)):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError(f'{name} must be an UTC datetime')
    if committed_at < cycle_at:
        raise ValueError('committed_at must not precede cycle_at')


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
