from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ada.alarms.core import (
    ConfigurationClosure,
    OccurrenceClosureReason,
    reconcile_group_configuration,
    reduce_initial_technical_incidents,
)
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecordV2,
    EngineCommitRecord,
    GroupCommitReference,
    GroupRuntimeSnapshot,
    prepare_configuration_rebase,
    prepare_group_commit,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import restore_group_lifecycle
from ada.alarms.persistence.operational.technical_incidents import snapshot_technical_incidents
from ada.processes.alarm_runtime.adoption import (
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionPlan,
)
from ada.processes.alarm_runtime.durable_recovery import RecoveredAlarmAuthority


@dataclass(frozen=True, slots=True)
class PreparedOperationalAdoption:
    adoption: ConfigurationAdoptionRecordV2
    group_records: tuple[EngineCommitRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adoption, ConfigurationAdoptionRecordV2):
            raise TypeError('operational adoption must use configuration adoption V2')
        if not self.group_records:
            raise ValueError('operational adoption requires group records')
        references = tuple(
            GroupCommitReference(
                priority_group=record.commit.priority_group,
                commit_id=record.commit.commit_id,
                record_hash=record.record_hash,
            )
            for record in self.group_records
        )
        if self.adoption.group_commits != references:
            raise ValueError('operational adoption group references do not match')


def prepare_operational_adoption(
    *,
    snapshots: tuple[GroupRuntimeSnapshot, ...],
    recovered: RecoveredAlarmAuthority,
    target: EngineAlarmConfiguration,
    target_ref: AlarmArtifactRefSnapshot,
    plan: ConfigurationAdoptionPlan,
    adoption_id: str,
    cycle_at: datetime,
    committed_at: datetime,
    runtime_artifact_version: str,
) -> PreparedOperationalAdoption:
    previous = recovered.lifecycle
    source_ref = recovered.artifact_ref
    if previous is None or source_ref is None:
        raise ValueError('operational adoption requires an EFFECTIVE lifecycle')
    if not snapshots:
        raise ValueError('operational adoption requires existing group snapshots')
    if not isinstance(target, EngineAlarmConfiguration):
        raise TypeError('target must be EngineAlarmConfiguration')
    if not isinstance(target_ref, AlarmArtifactRefSnapshot):
        raise TypeError('target_ref must be AlarmArtifactRefSnapshot')
    if plan.source != previous.configuration or plan.target != target or not plan.is_adoptable:
        raise ValueError('configuration adoption plan does not match an adoptable transition')
    if (
        source_ref.source_key != target_ref.source_key
        or source_ref.result_id == target_ref.result_id
    ):
        raise ValueError('configuration adoption artifact identity is invalid')
    old_revision = previous.configuration.resolution_key
    new_revision = target.resolution_key
    if (
        source_ref.alarm_configuration_revision != old_revision.alarm_configuration_revision
        or source_ref.confirmed_tool_catalog_revision
        != old_revision.confirmed_tool_catalog_revision
        or target_ref.alarm_configuration_revision != new_revision.alarm_configuration_revision
        or target_ref.confirmed_tool_catalog_revision
        != new_revision.confirmed_tool_catalog_revision
    ):
        raise ValueError('configuration revisions do not match exact artifact references')
    heads = dict(recovered.group_commit_ids)
    if len(heads) != len(snapshots):
        raise ValueError('snapshot inventory changed since durable recovery')
    plans_by_group: dict[str, list] = {}
    executable = {}
    for planned in target.planned_alarms:
        plans_by_group.setdefault(planned.priority_group, []).append(planned)
        executable[planned.identity] = planned.priority_group
    incident_reduction = reduce_initial_technical_incidents(
        previous.technical_incidents,
        evaluations=(),
        executable_groups=executable,
        cycle_at=cycle_at,
    )
    group_records: list[EngineCommitRecord] = []
    seen: set[str] = set()
    for snapshot in sorted(snapshots, key=lambda item: item.priority_group):
        group = snapshot.priority_group
        if group in seen or heads.get(group) != snapshot.last_commit_id:
            raise ValueError('group snapshot head changed since durable recovery')
        seen.add(group)
        before = snapshot.as_document()
        if before['state_basis'] != {
            'alarm_configuration_revision': source_ref.alarm_configuration_revision,
            'tool_registry_revision': source_ref.confirmed_tool_catalog_revision,
        }:
            raise ValueError('group snapshot revisions differ from source EFFECTIVE')
        prior = restore_group_lifecycle(snapshot)
        if previous.group_for(group) != prior:
            raise ValueError('group lifecycle differs from recovered durable state')
        previous_incidents = tuple(
            incident
            for incident in previous.technical_incidents
            if incident.priority_group == group
        )
        if snapshot_technical_incidents(snapshot) != previous_incidents:
            raise ValueError('group incidents differ from recovered durable state')
        closures = tuple(
            ConfigurationClosure(
                alarm_identity=change.identity,
                reason=(
                    OccurrenceClosureReason.CONFIGURATION_DISABLED
                    if change.disposition is ConfigurationAdoptionDisposition.DISABLED
                    else OccurrenceClosureReason.CONFIGURATION_REMOVED
                ),
                effective_at=cycle_at,
            )
            for change in plan.changes_for_group(group)
            if change.disposition
            in {ConfigurationAdoptionDisposition.DISABLED, ConfigurationAdoptionDisposition.REMOVED}
        )
        decision = reconcile_group_configuration(
            prior,
            effective_at=cycle_at,
            planned_alarms=tuple(plans_by_group.get(group, ())),
            configuration_closures=closures,
        )
        group_changes = tuple(
            change
            for change in incident_reduction.changes
            if change.incident.priority_group == group
        )
        group_incidents = tuple(
            incident
            for incident in incident_reduction.open_incidents
            if incident.priority_group == group
        )
        operational_change = bool(
            decision.state != prior
            or decision.occurrence_changes
            or decision.episode_changes
            or decision.technical_hold_changes
            or decision.management_effect_changes
            or decision.deactivation_effect_changes
            or decision.reappearance_changes
            or decision.cascade_suppressions
            or decision.assignment_changes
            or group_changes
        )
        if operational_change:
            prepared = prepare_group_commit(
                previous_snapshot=snapshot,
                previous_state=prior,
                decision=decision,
                evaluations=(),
                technical_incidents=group_incidents,
                technical_incident_changes=group_changes,
                cycle_at=cycle_at,
                committed_at=committed_at,
                alarm_configuration_revision=target_ref.alarm_configuration_revision,
                tool_registry_revision=target_ref.confirmed_tool_catalog_revision,
                runtime_artifact_version=runtime_artifact_version,
            )
            if prepared is None:
                raise ValueError('operational adoption could not materialize lifecycle changes')
            record = prepared.record
        else:
            record = prepare_configuration_rebase(
                previous_snapshot=snapshot,
                source_ref=source_ref,
                target_ref=target_ref,
                cycle_at=cycle_at,
                committed_at=committed_at,
                runtime_artifact_version=runtime_artifact_version,
            )
        group_records.append(record)
    if seen != set(heads):
        raise ValueError('snapshot inventory does not match recovered group heads')
    references = tuple(
        GroupCommitReference(
            priority_group=record.commit.priority_group,
            commit_id=record.commit.commit_id,
            record_hash=record.record_hash,
        )
        for record in group_records
    )
    adoption = ConfigurationAdoptionRecordV2.create(
        adoption_id=adoption_id,
        previous_artifact_ref=source_ref,
        target_artifact_ref=target_ref,
        effective_at=_utc(cycle_at),
        committed_at=_utc(committed_at),
        group_commits=references,
    )
    return PreparedOperationalAdoption(adoption=adoption, group_records=tuple(group_records))


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
