# Espejo pedagógico: prepara todos los grupos antes de escribir en el WAL.
# El lease protege la escritura y la memoria solo puede avanzar tras confirmar el batch.
# La adopción de configuración se rechaza explícitamente hasta el siguiente incremento.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from ada.alarms.core import GroupLifecycleState, resolve_management_cascades
from ada.alarms.persistence.operational.core_commit_bridge import prepare_group_commit
from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycleResult
from ada.processes.alarm_runtime.durable_recovery import RecoveredAlarmAuthority
from ada.processes.alarm_runtime.lifecycle import (
    AlarmLifecycleCycleResult,
    AlarmLifecycleRuntimeState,
)
from atlanticus.runtime import JobRuntimeContext

RUNTIME_ARTIFACT_VERSION = 'ada-alarm-runtime-process/1.0.0'


class AlarmRuntimeDurabilityError(RuntimeError):
    pass


@runtime_checkable
class AlarmOperationalCommitStore(Protocol):
    def read_snapshot(self, priority_group: str): ...

    def commit_batch(self, records, *, assert_authority, fenced_mutation): ...


@dataclass(frozen=True, slots=True)
class AlarmDurableCycleCommitter:
    persistence: AlarmOperationalCommitStore

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, AlarmOperationalCommitStore):
            raise TypeError('persistence must support operational group commits')

    def commit(
        self,
        context: JobRuntimeContext,
        *,
        recovered: RecoveredAlarmAuthority,
        previous: AlarmLifecycleRuntimeState,
        cycle: AlarmEvaluationCycleResult,
        lifecycle: AlarmLifecycleCycleResult,
    ) -> AlarmLifecycleRuntimeState:
        if not isinstance(recovered, RecoveredAlarmAuthority) or recovered.artifact_ref is None:
            raise AlarmRuntimeDurabilityError('durable cycle requires recovered EFFECTIVE authority')
        if not isinstance(previous, AlarmLifecycleRuntimeState):
            raise TypeError('previous must be AlarmLifecycleRuntimeState')
        if not isinstance(cycle, AlarmEvaluationCycleResult):
            raise TypeError('cycle must be AlarmEvaluationCycleResult')
        if not isinstance(lifecycle, AlarmLifecycleCycleResult):
            raise TypeError('lifecycle must be AlarmLifecycleCycleResult')
        if cycle.cycle_at != lifecycle.cycle_at:
            raise AlarmRuntimeDurabilityError('evaluation and lifecycle timestamps differ')
        if lifecycle.adoption_plan is not None or any(
            group.adoption_decision is not None for group in lifecycle.groups
        ):
            raise AlarmRuntimeDurabilityError('configuration adoption requires durable adoption')
        if previous.configuration != lifecycle.state.configuration:
            raise AlarmRuntimeDurabilityError('cycle cannot change EFFECTIVE configuration')
        key = previous.configuration.resolution_key
        reference = recovered.artifact_ref
        if (
            key.alarm_configuration_revision != reference.alarm_configuration_revision
            or key.confirmed_tool_catalog_revision != reference.confirmed_tool_catalog_revision
        ):
            raise AlarmRuntimeDurabilityError('EFFECTIVE revisions differ from runtime session')
        expected_groups = {
            plan.priority_group for plan in previous.configuration.planned_alarms
        }
        expected_groups.update(item.priority_group for item in previous.groups)
        expected_groups.update(item.priority_group for item in previous.technical_incidents)
        if not expected_groups.issubset(
            {group.priority_group for group in lifecycle.groups}
        ):
            raise AlarmRuntimeDurabilityError('lifecycle omitted a required priority group')
        context.assert_lease_current()
        changes = lifecycle.technical_incident_changes
        known = {
            plan.identity: plan.priority_group
            for plan in previous.configuration.planned_alarms
        }
        current = {item.priority_group: item for item in previous.groups}
        prepared_records = []
        updated: dict[str, GroupLifecycleState] = dict(current)
        for group in lifecycle.groups:
            group_key = group.priority_group
            old = current.get(group_key, GroupLifecycleState(priority_group=group_key))
            snapshot = self.persistence.read_snapshot(group_key)
            relevant_changes = tuple(
                change for change in changes if change.incident.priority_group == group_key
            )
            group_incidents = tuple(
                item for item in lifecycle.state.technical_incidents
                if item.priority_group == group_key
            )
            evaluations = tuple(
                item for item in cycle.evaluations
                if known.get(item.alarm_identity) == group_key
            )
            planned = tuple(
                plan for plan in previous.configuration.planned_alarms
                if plan.priority_group == group_key
            )
            previous_evaluations = (
                alarm.last_evaluation.evaluated_at
                for alarm in old.alarms if alarm.last_evaluation is not None
            )
            prior_at = max(previous_evaluations, default=cycle.cycle_at)
            if prior_at > cycle.cycle_at:
                raise AlarmRuntimeDurabilityError('Prior cascade state is ahead of cycle')
            previous_cascades = resolve_management_cascades(
                old, planned_alarms=planned, at=prior_at
            )
            prepared = prepare_group_commit(
                previous_snapshot=snapshot,
                previous_state=old,
                decision=group.decision,
                evaluations=evaluations,
                technical_incidents=group_incidents,
                technical_incident_changes=relevant_changes,
                cycle_at=cycle.cycle_at,
                committed_at=max(cycle.cycle_at, datetime.now(UTC)),
                alarm_configuration_revision=reference.alarm_configuration_revision,
                tool_registry_revision=reference.confirmed_tool_catalog_revision,
                runtime_artifact_version=RUNTIME_ARTIFACT_VERSION,
                previous_priority_resolution=None,
                previous_cascade_suppressions=previous_cascades,
            )
            if prepared is None:
                if group.decision.state != old:
                    raise AlarmRuntimeDurabilityError(
                        'lifecycle changed without a durable commit'
                    )
                continue
            prepared_records.append(prepared.record)
            updated[group_key] = prepared.state
        if not prepared_records:
            if lifecycle.state.technical_incidents != previous.technical_incidents:
                raise AlarmRuntimeDurabilityError('technical incidents changed without a commit')
            context.assert_lease_current()
            return previous
        context.assert_lease_current()
        self.persistence.commit_batch(
            tuple(prepared_records),
            assert_authority=context.assert_lease_current,
            fenced_mutation=context.fenced_mutation,
        )
        context.assert_lease_current()
        return AlarmLifecycleRuntimeState(
            configuration=previous.configuration,
            groups=tuple(updated.values()),
            technical_incidents=lifecycle.state.technical_incidents,
        )
