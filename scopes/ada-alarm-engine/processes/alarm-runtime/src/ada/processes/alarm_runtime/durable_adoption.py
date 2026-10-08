from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import uuid4

from ada.alarms.materialization import AlarmResolutionStatus
from ada.alarms.persistence import ReadyAlarmMaterialization
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    GroupRuntimeSnapshot,
    prepare_noop_configuration_adoption,
)
from ada.processes.alarm_runtime.adoption import plan_configuration_adoption
from ada.processes.alarm_runtime.durable_commit import RUNTIME_ARTIFACT_VERSION
from ada.processes.alarm_runtime.durable_recovery import RecoveredAlarmAuthority
from ada.processes.alarm_runtime.operational_adoption import prepare_operational_adoption
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
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key.strip() != self.source_key
        ):
            raise ValueError('source_key must be non-empty text')
        if not callable(self.clock):
            raise TypeError('clock must be callable')

    def read_candidate(self) -> ReadyAlarmMaterialization | None:
        return self.materializations.read_published_ready(source_key=self.source_key)

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
        context.assert_lease_current()
        cycle_at = self.clock()
        if (
            not isinstance(cycle_at, datetime)
            or cycle_at.tzinfo is None
            or cycle_at.utcoffset() != UTC.utcoffset(cycle_at)
        ):
            raise ValueError('adoption clock must return a UTC datetime')
        snapshots = self.persistence.list_snapshots()
        adoption_id = f'alarm-adoption-{uuid4().hex}'
        committed_at = max(cycle_at, datetime.now(UTC))
        if recovered.lifecycle is None:
            if snapshots:
                raise AlarmOperationalAdoptionRequired(
                    'bootstrap cannot replace existing snapshots'
                )
            prepared = prepare_noop_configuration_adoption(
                snapshots=(),
                source_ref=source_ref,
                target_ref=target_ref,
                adoption_id=adoption_id,
                cycle_at=cycle_at,
                committed_at=committed_at,
                runtime_artifact_version=RUNTIME_ARTIFACT_VERSION,
            )
        elif snapshots:
            prepared = prepare_operational_adoption(
                snapshots=snapshots,
                recovered=recovered,
                target=ready.engine,
                target_ref=target_ref,
                plan=plan,
                adoption_id=adoption_id,
                cycle_at=cycle_at,
                committed_at=committed_at,
                runtime_artifact_version=RUNTIME_ARTIFACT_VERSION,
            )
        else:
            prepared = prepare_noop_configuration_adoption(
                snapshots=(),
                source_ref=source_ref,
                target_ref=target_ref,
                adoption_id=adoption_id,
                cycle_at=cycle_at,
                committed_at=committed_at,
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
