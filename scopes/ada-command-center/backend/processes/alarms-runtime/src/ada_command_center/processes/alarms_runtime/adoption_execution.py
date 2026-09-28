from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ada_command_center.alarms.core import (
    ConfigurationClosure,
    GroupCommitMaterialization,
    GroupLifecycleDecision,
    OccurrenceClosureReason,
    materialize_group_commit,
    reconcile_group_configuration,
    resolve_group_priority,
    resolve_management_cascades,
)
from ada_command_center.alarms.materialization.artifact_reference import (
    AlarmConfigurationArtifactRef,
)
from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    CommitBatchResult,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    EngineCommitRecord,
    GroupCommitReference,
)
from ada_command_center.processes.alarms_runtime.adoption import (
    AlarmConfigurationRevision,
    ConfigurationAdoptionChange,
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionPlan,
)
from ada_command_center.processes.alarms_runtime.commit import compose_engine_commit_record
from ada_command_center.processes.alarms_runtime.composition import AlarmRuntimeComposition
from ada_command_center.processes.alarms_runtime.cycle import AlarmCommitTimeProvider
from ada_command_center.processes.alarms_runtime.session import AlarmExecutionSession
from atlanticus.runtime import JobRuntimeContext


class ConfigurationAdoptionExecutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionGroupResult:
    priority_group: str
    decision: GroupLifecycleDecision
    materialization: GroupCommitMaterialization | None

    def __post_init__(self) -> None:
        if not isinstance(self.priority_group, str) or not self.priority_group.strip():
            raise ValueError('priority_group must be a non-empty string')
        if not isinstance(self.decision, GroupLifecycleDecision):
            raise TypeError('decision must be GroupLifecycleDecision')
        if self.decision.state.priority_group != self.priority_group:
            raise ConfigurationAdoptionExecutionError(
                'group decision priority_group must match adoption result priority_group'
            )
        if self.materialization is not None:
            if not isinstance(self.materialization, GroupCommitMaterialization):
                raise TypeError('materialization must be GroupCommitMaterialization or None')
            if self.materialization.commit.priority_group != self.priority_group:
                raise ConfigurationAdoptionExecutionError(
                    'group materialization priority_group must match adoption result priority_group'
                )


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionExecutionResult:
    plan: ConfigurationAdoptionPlan
    effective_at: datetime
    groups: tuple[ConfigurationAdoptionGroupResult, ...]
    adoption_record: ConfigurationAdoptionRecord
    commit_result: CommitBatchResult

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ConfigurationAdoptionPlan):
            raise TypeError('plan must be ConfigurationAdoptionPlan')
        _require_utc_datetime(self.effective_at, 'effective_at')
        if not isinstance(self.groups, tuple) or not all(
            isinstance(item, ConfigurationAdoptionGroupResult) for item in self.groups
        ):
            raise TypeError('groups must contain ConfigurationAdoptionGroupResult values')
        group_keys = tuple(item.priority_group for item in self.groups)
        if group_keys != tuple(sorted(set(group_keys))):
            raise ConfigurationAdoptionExecutionError(
                'adoption group results must be unique and sorted by priority_group'
            )
        if not isinstance(self.adoption_record, ConfigurationAdoptionRecord):
            raise TypeError('adoption_record must be a ConfigurationAdoptionRecord')
        if not isinstance(self.commit_result, CommitBatchResult):
            raise TypeError('commit_result must be a CommitBatchResult')
        if self.commit_result.record_count != len(self.materializations) + 1:
            raise ConfigurationAdoptionExecutionError(
                'commit_result must contain all group commits and one global adoption'
            )
        if self.adoption_record.target_artifact_ref != _artifact_snapshot(
            self.plan.target.artifact_ref
        ):
            raise ConfigurationAdoptionExecutionError(
                'adoption record target must match the planned configuration'
            )

    @property
    def session(self) -> AlarmExecutionSession:
        return self.plan.target.session

    @property
    def materializations(self) -> tuple[GroupCommitMaterialization, ...]:
        return tuple(
            group.materialization for group in self.groups if group.materialization is not None
        )


@dataclass(slots=True)
class AlarmConfigurationAdoptionExecutor:
    composition: AlarmRuntimeComposition
    commit_time_provider: AlarmCommitTimeProvider
    runtime_artifact_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.composition, AlarmRuntimeComposition):
            raise TypeError('composition must be AlarmRuntimeComposition')
        if not isinstance(self.commit_time_provider, AlarmCommitTimeProvider):
            raise TypeError('commit_time_provider must implement AlarmCommitTimeProvider')
        if (
            not isinstance(self.runtime_artifact_version, str)
            or not self.runtime_artifact_version.strip()
        ):
            raise ValueError('runtime_artifact_version must be a non-empty string')
        self.runtime_artifact_version = self.runtime_artifact_version.strip()

    def prepare(
        self,
        plan: ConfigurationAdoptionPlan,
        *,
        effective_at: datetime,
    ) -> tuple[ConfigurationAdoptionGroupResult, ...]:
        return self._prepare_groups(plan, effective_at=effective_at, committed_at=None)

    def bootstrap(
        self,
        context: JobRuntimeContext,
        target: AlarmConfigurationRevision,
        *,
        effective_at: datetime,
        adoption_id: str,
    ) -> CommitBatchResult:
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be JobRuntimeContext')
        if not isinstance(target, AlarmConfigurationRevision):
            raise TypeError('target must be AlarmConfigurationRevision')
        _require_utc_datetime(effective_at, 'effective_at')
        _require_adoption_id(adoption_id)
        persistence = self.composition.durability.persistence
        if not persistence.read_head().aligned:
            raise ConfigurationAdoptionExecutionError(
                'Alarm Engine journal must be recovered before configuration adoption'
            )
        if persistence.read_effective_head() is not None:
            raise ConfigurationAdoptionExecutionError(
                'bootstrap requires absence of an EFFECTIVE configuration'
            )
        committed_at = self._committed_at(effective_at)
        record = ConfigurationAdoptionRecord.create(
            adoption_id=adoption_id,
            previous_artifact_ref=None,
            target_artifact_ref=_artifact_snapshot(target.artifact_ref),
            effective_at=_utc_text(effective_at),
            committed_at=_utc_text(committed_at),
        )
        result = self.composition.durability.commit_adoption(context, record)
        self._assert_confirmed(record)
        return result

    def execute(
        self,
        context: JobRuntimeContext,
        plan: ConfigurationAdoptionPlan,
        *,
        effective_at: datetime,
        adoption_id: str,
    ) -> ConfigurationAdoptionExecutionResult:
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be JobRuntimeContext')
        if not isinstance(plan, ConfigurationAdoptionPlan):
            raise TypeError('plan must be ConfigurationAdoptionPlan')
        _require_utc_datetime(effective_at, 'effective_at')
        _require_adoption_id(adoption_id)
        persistence = self.composition.durability.persistence
        before_head = persistence.read_head()
        if not before_head.aligned:
            raise ConfigurationAdoptionExecutionError(
                'Alarm Engine journal must be recovered before configuration adoption'
            )
        effective = persistence.read_effective_head()
        if effective is None:
            raise ConfigurationAdoptionExecutionError(
                'initial configuration requires bootstrap before adopting a new revision'
            )
        source_ref = _artifact_snapshot(plan.source.artifact_ref)
        if effective.target_artifact_ref != source_ref:
            raise ConfigurationAdoptionExecutionError(
                'adoption source does not match the current EFFECTIVE configuration'
            )
        committed_at = self._committed_at(effective_at)
        groups = self._prepare_groups(
            plan,
            effective_at=effective_at,
            committed_at=committed_at,
        )
        if persistence.read_head() != before_head:
            raise ConfigurationAdoptionExecutionError(
                'Alarm Engine journal changed during configuration adoption preparation'
            )
        if persistence.read_effective_head() != effective:
            raise ConfigurationAdoptionExecutionError(
                'EFFECTIVE changed during configuration adoption preparation'
            )
        group_records = self._compose_group_records(groups)
        target_ref = _artifact_snapshot(plan.target.artifact_ref)
        record_fields = {
            'adoption_id': adoption_id,
            'previous_artifact_ref': source_ref,
            'target_artifact_ref': target_ref,
            'effective_at': _utc_text(effective_at),
            'committed_at': _utc_text(committed_at),
        }
        if group_records:
            record = ConfigurationAdoptionRecordV2.create(
                **record_fields,
                group_commits=tuple(
                    GroupCommitReference(
                        priority_group=item.commit.priority_group,
                        commit_id=item.commit.commit_id,
                        record_hash=item.record_hash,
                    )
                    for item in group_records
                ),
            )
        else:
            record = ConfigurationAdoptionRecord.create(**record_fields)
        if persistence.read_head() != before_head:
            raise ConfigurationAdoptionExecutionError(
                'Alarm Engine journal changed during configuration adoption preparation'
            )
        commit_result = self.composition.durability.commit_adoption(
            context, record, group_records=group_records
        )
        self._assert_confirmed(record)
        return ConfigurationAdoptionExecutionResult(
            plan=plan,
            effective_at=effective_at,
            groups=groups,
            adoption_record=record,
            commit_result=commit_result,
        )

    def _prepare_groups(
        self,
        plan: ConfigurationAdoptionPlan,
        *,
        effective_at: datetime,
        committed_at: datetime | None,
    ) -> tuple[ConfigurationAdoptionGroupResult, ...]:
        if not isinstance(plan, ConfigurationAdoptionPlan):
            raise TypeError('plan must be ConfigurationAdoptionPlan')
        _require_utc_datetime(effective_at, 'effective_at')
        if not plan.is_adoptable:
            reasons = ', '.join(
                f'{change.identity.canonical_key}:{change.rejection_reason.value}'
                for change in plan.rejected_changes
            )
            raise ConfigurationAdoptionExecutionError(
                f'configuration adoption plan is rejected: {reasons}'
            )
        if not self.composition.durability.persistence.read_head().aligned:
            raise ConfigurationAdoptionExecutionError(
                'Alarm Engine journal must be recovered before configuration adoption'
            )
        grouped_changes = self._grouped_changes(plan)
        if not grouped_changes:
            return ()
        resolved_committed_at = (
            self._committed_at(effective_at) if committed_at is None else committed_at
        )
        return tuple(
            self._prepare_group(
                plan,
                priority_group=priority_group,
                changes=changes,
                effective_at=effective_at,
                committed_at=resolved_committed_at,
            )
            for priority_group, changes in sorted(grouped_changes.items())
        )

    def _compose_group_records(
        self,
        groups: tuple[ConfigurationAdoptionGroupResult, ...],
    ) -> tuple[EngineCommitRecord, ...]:
        persistence = self.composition.durability.persistence
        return tuple(
            compose_engine_commit_record(
                group.materialization,
                previous_snapshot=persistence.read_snapshot(group.priority_group),
            )
            for group in groups
            if group.materialization is not None
        )

    def _assert_confirmed(self, record: ConfigurationAdoptionRecord) -> None:
        effective = self.composition.durability.persistence.read_effective_head()
        if (
            effective is None
            or effective.adoption_id != record.adoption_id
            or effective.adoption_record_hash != record.record_hash
            or effective.target_artifact_ref != record.target_artifact_ref
        ):
            raise ConfigurationAdoptionExecutionError(
                'confirmed EFFECTIVE does not match the durable configuration adoption'
            )

    def _grouped_changes(
        self,
        plan: ConfigurationAdoptionPlan,
    ) -> dict[str, tuple[ConfigurationAdoptionChange, ...]]:
        grouped: dict[str, list[ConfigurationAdoptionChange]] = {}
        for change in plan.changes:
            if change.disposition is ConfigurationAdoptionDisposition.UNCHANGED:
                continue
            source_plan = plan.source.plan_for(change.identity)
            target_plan = plan.target.plan_for(change.identity)
            if source_plan is None and target_plan is None:
                if change.disposition in {
                    ConfigurationAdoptionDisposition.ADDED,
                    ConfigurationAdoptionDisposition.REMOVED,
                }:
                    continue
                raise ConfigurationAdoptionExecutionError(
                    f'{change.identity.canonical_key}: adoption group cannot be resolved'
                )
            selected_plan = source_plan if source_plan is not None else target_plan
            grouped.setdefault(selected_plan.priority_group, []).append(change)
        return {priority_group: tuple(changes) for priority_group, changes in grouped.items()}

    def _prepare_group(
        self,
        plan: ConfigurationAdoptionPlan,
        *,
        priority_group: str,
        changes: tuple[ConfigurationAdoptionChange, ...],
        effective_at: datetime,
        committed_at: datetime,
    ) -> ConfigurationAdoptionGroupResult:
        source_plans = tuple(
            entry.planned_alarm
            for entry in plan.source.session.entries
            if entry.planned_alarm.priority_group == priority_group
        )
        target_plans = tuple(
            entry.planned_alarm
            for entry in plan.target.session.entries
            if entry.planned_alarm.priority_group == priority_group
        )
        runtime_group = self.composition.load_group(
            priority_group,
            planned_alarms=source_plans,
        )
        previous_priority_resolution = resolve_group_priority(
            runtime_group.state,
            planned_alarms=source_plans,
            cascade_suppressions=resolve_management_cascades(
                runtime_group.state,
                planned_alarms=source_plans,
                at=effective_at,
            ),
        )
        closures = tuple(
            ConfigurationClosure(
                alarm_identity=change.identity,
                reason=(
                    OccurrenceClosureReason.CONFIGURATION_DISABLED
                    if change.disposition is ConfigurationAdoptionDisposition.DISABLED
                    else OccurrenceClosureReason.CONFIGURATION_REMOVED
                ),
                effective_at=effective_at,
            )
            for change in changes
            if change.disposition
            in {
                ConfigurationAdoptionDisposition.DISABLED,
                ConfigurationAdoptionDisposition.REMOVED,
            }
        )
        structural_reset = any(
            change.disposition is ConfigurationAdoptionDisposition.STRUCTURAL_RESET
            for change in changes
        )
        decision = reconcile_group_configuration(
            runtime_group.state,
            effective_at=effective_at,
            planned_alarms=target_plans,
            configuration_closures=closures,
            structural_reset=structural_reset,
        )
        materialization = materialize_group_commit(
            runtime_group.state,
            decision,
            evaluations=(),
            cycle_at=effective_at,
            committed_at=committed_at,
            alarm_configuration_revision=plan.target.alarm_configuration_revision,
            tool_registry_revision=plan.target.tool_registry_revision,
            runtime_artifact_version=self.runtime_artifact_version,
            previous_commit_id=runtime_group.last_commit_id,
            previous_priority_resolution=previous_priority_resolution,
        )
        return ConfigurationAdoptionGroupResult(
            priority_group=priority_group,
            decision=decision,
            materialization=materialization,
        )

    def _committed_at(self, effective_at: datetime) -> datetime:
        committed_at = self.commit_time_provider.committed_at(cycle_at=effective_at)
        if not isinstance(committed_at, datetime):
            raise TypeError('commit_time_provider must return datetime')
        if committed_at.tzinfo is None or committed_at.utcoffset() != timedelta(0):
            raise ValueError('committed_at must be timezone-aware UTC')
        if committed_at < effective_at:
            raise ValueError('committed_at must not be before effective_at')
        return committed_at


def _require_utc_datetime(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f'{name} must be a datetime')
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f'{name} must be timezone-aware UTC')


def _artifact_snapshot(ref: AlarmConfigurationArtifactRef) -> AlarmArtifactRefSnapshot:
    return AlarmArtifactRefSnapshot(
        source_key=ref.source_key,
        result_id=ref.result_id,
        manifest_sha256=ref.manifest_sha256,
        alarm_configuration_revision=ref.resolution_key.alarm_configuration_revision,
        confirmed_tool_catalog_revision=ref.resolution_key.confirmed_tool_catalog_revision,
    )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _require_adoption_id(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('adoption_id must be non-empty text without surrounding whitespace')
