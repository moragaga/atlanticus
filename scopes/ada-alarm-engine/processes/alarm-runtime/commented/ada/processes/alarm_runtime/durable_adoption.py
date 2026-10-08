# Espejo pedagógico: habilita adopción de configuración solo cuando no requiere transiciones físicas.
# READY no otorga autoridad; primero se confirma en el WAL, después se relee EFFECTIVE.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import uuid4

from ada.alarms.core import (
    ConfigurationClosure,
    OccurrenceClosureReason,
    reconcile_group_configuration,
)
from ada.alarms.materialization import AlarmResolutionStatus, EngineAlarmConfiguration
from ada.alarms.persistence import ReadyAlarmMaterialization
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    GroupRuntimeSnapshot,
    prepare_noop_configuration_adoption,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import restore_group_lifecycle
from ada.processes.alarm_runtime.adoption import (
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionPlan,
    plan_configuration_adoption,
)
from ada.processes.alarm_runtime.durable_commit import RUNTIME_ARTIFACT_VERSION
from ada.processes.alarm_runtime.durable_recovery import RecoveredAlarmAuthority
from atlanticus.runtime import JobRuntimeContext


class AlarmOperationalAdoptionRequired(RuntimeError):
    pass


@runtime_checkable
class AlarmPublishedReadyReader(Protocol):
    def read_published_ready(self, *, source_key: str) -> ReadyAlarmMaterialization | None: ...


@runtime_checkable
class AlarmOperationalAdoptionStore(Protocol):
    def list_snapshots(self) -> tuple[GroupRuntimeSnapshot, ...]: ...

    def commit_adoption(
        self, record, *, group_records=(), assert_authority, fenced_mutation
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class AlarmDurableAdopter:
    persistence: AlarmOperationalAdoptionStore
    materializations: AlarmPublishedReadyReader
    source_key: str
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, AlarmOperationalAdoptionStore):
            raise TypeError('persistence must support durable configuration adoption')
        if not isinstance(self.materializations, AlarmPublishedReadyReader):
            raise TypeError('materializations must support published READY lookup')
        if not isinstance(self.source_key, str) or not self.source_key or self.source_key.strip() != self.source_key:
            raise ValueError('source_key must be non-empty text')
        if not callable(self.clock):
            raise TypeError('clock must be callable')

    def read_candidate(self) -> ReadyAlarmMaterialization | None:
        return self.materializations.read_published_ready(source_key=self.source_key)

    # Reconstruye la identidad exacta del READY: nombre, manifest y revisiones.
    def reference_for(self, ready: ReadyAlarmMaterialization) -> AlarmArtifactRefSnapshot:
        manifest = ready.manifest
        if (
            manifest.source_key != self.source_key
            or manifest.result_id != ready.result_id
            or manifest.status is not AlarmResolutionStatus.READY
            or manifest.resolution_key != ready.engine.resolution_key
        ):
            raise ValueError('published READY identity or resolution is inconsistent')
        return AlarmArtifactRefSnapshot(
            source_key=self.source_key,
            result_id=ready.result_id,
            manifest_sha256=ready.manifest_sha256,
            alarm_configuration_revision=manifest.resolution_key.alarm_configuration_revision,
            confirmed_tool_catalog_revision=manifest.resolution_key.confirmed_tool_catalog_revision,
        )

    # Prepara una sola adopción V1 o V2 protegida por el fencing del lease.
    # Si la persistencia falla, ninguna sesión o lifecycle se publica aquí en memoria.
    def adopt(
        self,
        context: JobRuntimeContext,
        *,
        recovered: RecoveredAlarmAuthority,
        ready: ReadyAlarmMaterialization,
    ) -> AlarmArtifactRefSnapshot:
        if not isinstance(recovered, RecoveredAlarmAuthority):
            raise TypeError('recovered must be RecoveredAlarmAuthority')
        target_ref = self.reference_for(ready)
        source_ref = recovered.artifact_ref
        if source_ref == target_ref:
            raise ValueError('EFFECTIVE already identifies this READY artifact')
        if recovered.lifecycle is not None:
            plan = plan_configuration_adoption(recovered.lifecycle.configuration, ready.engine)
            if not plan.is_adoptable:
                raise ValueError('new READY configuration is not adoptable')
        else:
            plan = None
        context.assert_lease_current()
        cycle_at = self.clock()
        if (
            not isinstance(cycle_at, datetime)
            or cycle_at.tzinfo is None
            or cycle_at.utcoffset() != UTC.utcoffset(cycle_at)
        ):
            raise ValueError('adoption clock must return a UTC datetime')
        snapshots = self.persistence.list_snapshots()
        if recovered.lifecycle is None:
            if snapshots:
                raise AlarmOperationalAdoptionRequired('bootstrap cannot replace existing snapshots')
        else:
            self._require_non_operational_adoption(
                snapshots=snapshots,
                recovered=recovered,
                target=ready.engine,
                plan=plan,
                at=cycle_at,
            )
        prepared = prepare_noop_configuration_adoption(
            snapshots=snapshots,
            source_ref=source_ref,
            target_ref=target_ref,
            adoption_id=f'alarm-adoption-{uuid4().hex}',
            cycle_at=cycle_at,
            committed_at=max(cycle_at, datetime.now(UTC)),
            runtime_artifact_version=RUNTIME_ARTIFACT_VERSION,
        )
        context.assert_lease_current()
        self.persistence.commit_adoption(
            prepared.adoption,
            group_records=prepared.group_records,
            assert_authority=context.assert_lease_current,
            fenced_mutation=context.fenced_mutation,
        )
        context.assert_lease_current()
        return target_ref

    # Compara el resultado de reconciliar el nuevo plan con la autoridad anterior.
    # Un cambio operacional requiere otro contrato para agrupar eventos y rebase en el mismo WAL.
    @staticmethod
    def _require_non_operational_adoption(
        *,
        snapshots: tuple[GroupRuntimeSnapshot, ...],
        recovered: RecoveredAlarmAuthority,
        target: EngineAlarmConfiguration,
        plan: ConfigurationAdoptionPlan,
        at: datetime,
    ) -> None:
        previous = recovered.lifecycle
        if previous is None:
            raise ValueError('source lifecycle is required')
        if len(snapshots) != len(recovered.group_commit_ids):
            raise AlarmOperationalAdoptionRequired('snapshot inventory changed since recovery')
        heads = dict(recovered.group_commit_ids)
        plans_by_group: dict[str, list] = {}
        for planned in target.planned_alarms:
            plans_by_group.setdefault(planned.priority_group, []).append(planned)
        executable = {planned.identity: planned.priority_group for planned in target.planned_alarms}
        for incident in previous.technical_incidents:
            if executable.get(incident.alarm_identity) != incident.priority_group:
                raise AlarmOperationalAdoptionRequired('adoption must resolve withdrawn technical incidents')
        for snapshot in snapshots:
            if heads.get(snapshot.priority_group) != snapshot.last_commit_id:
                raise AlarmOperationalAdoptionRequired('group head changed since recovery')
            prior = restore_group_lifecycle(snapshot)
            planned_alarms = tuple(plans_by_group.get(snapshot.priority_group, ()))
            changes = plan.changes_for_group(snapshot.priority_group)
            closures = tuple(
                ConfigurationClosure(
                    alarm_identity=change.identity,
                    reason=(
                        OccurrenceClosureReason.CONFIGURATION_DISABLED
                        if change.disposition is ConfigurationAdoptionDisposition.DISABLED
                        else OccurrenceClosureReason.CONFIGURATION_REMOVED
                    ),
                    effective_at=at,
                )
                for change in changes
                if change.disposition in {
                    ConfigurationAdoptionDisposition.DISABLED,
                    ConfigurationAdoptionDisposition.REMOVED,
                }
            )
            decision = reconcile_group_configuration(
                prior,
                effective_at=at,
                planned_alarms=planned_alarms,
                configuration_closures=closures,
            )
            if (
                decision.state != prior
                or decision.occurrence_changes
                or decision.episode_changes
                or decision.technical_hold_changes
                or decision.management_effect_changes
                or decision.deactivation_effect_changes
                or decision.reappearance_changes
                or decision.cascade_suppressions
                or decision.assignment_changes
            ):
                raise AlarmOperationalAdoptionRequired(
                    'adoption requires durable operational lifecycle transitions'
                )
