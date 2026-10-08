# Lector recuperable de la autoridad operacional de Alarm Engine.
# Este componente no promueve nuevas configuraciones ni escribe memoria del job.
# El WAL confirmado se recupera siempre bajo la autoridad del lease de Atlanticus.
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ada.alarms.core import TechnicalIncident
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.alarms.persistence import ReadyAlarmMaterialization
from ada.alarms.persistence.operational import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    GroupRuntimeSnapshot,
    JournalHead,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import restore_group_lifecycle
from ada.alarms.persistence.operational.technical_incidents import snapshot_technical_incidents
from ada.contracts.alarms import AlarmIdentity
from ada.processes.alarm_runtime.lifecycle import AlarmLifecycleRuntimeState
from atlanticus.runtime import JobRuntimeContext


class AlarmDurableRecoveryError(RuntimeError):
    # La recuperación no debe inventar datos faltantes ni ignorar discrepancias.
    pass


@runtime_checkable
class AlarmOperationalRecoveryStore(Protocol):
    # Contrato existente de escritura física protegida por lease.
    def recover(
        self,
        *,
        assert_authority: Callable[[], None],
        fenced_mutation: Callable[[], AbstractContextManager[None]],
    ) -> object: ...

    def read_head(self) -> JournalHead: ...

    def read_effective_head(self) -> AlarmEffectiveConfigurationHead | None: ...

    def list_snapshots(self) -> tuple[GroupRuntimeSnapshot, ...]: ...


@runtime_checkable
class AlarmVersionedReadyReader(Protocol):
    # La identidad READY viene del EFFECTIVE durable, jamás del puntero más reciente.
    def read_ready(
        self,
        *,
        source_key: str,
        result_id: str,
        expected_manifest_sha256: str | None = None,
    ) -> ReadyAlarmMaterialization: ...


@dataclass(frozen=True, slots=True)
class RecoveredAlarmAuthority:
    artifact_ref: AlarmArtifactRefSnapshot | None
    lifecycle: AlarmLifecycleRuntimeState | None
    group_commit_ids: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (self.artifact_ref is None) != (self.lifecycle is None):
            raise ValueError('artifact_ref and lifecycle must both be present or absent')
        if self.artifact_ref is not None and not isinstance(
            self.artifact_ref, AlarmArtifactRefSnapshot
        ):
            raise TypeError('artifact_ref must be an AlarmArtifactRefSnapshot')
        if self.lifecycle is not None and not isinstance(
            self.lifecycle, AlarmLifecycleRuntimeState
        ):
            raise TypeError('lifecycle must be an AlarmLifecycleRuntimeState')
        if self.group_commit_ids != tuple(sorted(self.group_commit_ids)):
            raise ValueError('group commit IDs must be sorted')
        if len({key for key, _ in self.group_commit_ids}) != len(self.group_commit_ids):
            raise ValueError('group commit IDs must be unique by priority_group')
        if self.lifecycle is None and self.group_commit_ids:
            raise ValueError('group commits require an effective artifact')


@dataclass(frozen=True, slots=True)
class AlarmDurableRecovery:
    persistence: AlarmOperationalRecoveryStore
    materializations: AlarmVersionedReadyReader
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, AlarmOperationalRecoveryStore):
            raise TypeError('persistence must support operational recovery')
        if not isinstance(self.materializations, AlarmVersionedReadyReader):
            raise TypeError('materializations must support exact READY lookup')
        if not isinstance(self.source_key, str) or not self.source_key.strip():
            raise ValueError('source_key must be non-empty text')

    def recover(self, context: JobRuntimeContext) -> RecoveredAlarmAuthority:
        # Jamás interpretar un snapshot parcialmente materializado como estado confirmado.
        context.assert_lease_current()
        self.persistence.recover(
            assert_authority=context.assert_lease_current,
            fenced_mutation=context.fenced_mutation,
        )
        context.assert_lease_current()
        head = self.persistence.read_head()
        if not head.aligned:
            raise AlarmDurableRecoveryError('WAL recovery did not align durable head')
        effective = self.persistence.read_effective_head()
        snapshots = self.persistence.list_snapshots()
        if effective is None:
            if head.durable is not None or snapshots:
                raise AlarmDurableRecoveryError(
                    'durable WAL state requires explicit effective configuration migration'
                )
            context.assert_lease_current()
            return RecoveredAlarmAuthority(artifact_ref=None, lifecycle=None)
        reference = effective.target_artifact_ref
        if reference.source_key != self.source_key:
            raise AlarmDurableRecoveryError('EFFECTIVE artifact source does not match Runtime')
        # El digest y el result_id se validan contra la version inmutable de materialización.
        ready = self.materializations.read_ready(
            source_key=reference.source_key,
            result_id=reference.result_id,
            expected_manifest_sha256=reference.manifest_sha256,
        )
        if (
            ready.result_id != reference.result_id
            or ready.manifest_sha256 != reference.manifest_sha256
        ):
            raise AlarmDurableRecoveryError('READY artifact identity differs from EFFECTIVE')
        configuration = ready.engine
        if not isinstance(configuration, EngineAlarmConfiguration):
            raise AlarmDurableRecoveryError('READY engine configuration is invalid')
        resolution_key = configuration.resolution_key
        if (
            resolution_key.alarm_configuration_revision
            != reference.alarm_configuration_revision
            or resolution_key.confirmed_tool_catalog_revision
            != reference.confirmed_tool_catalog_revision
            or ready.manifest.resolution_key != resolution_key
        ):
            raise AlarmDurableRecoveryError('READY revisions differ from EFFECTIVE')
        groups = []
        incidents: list[TechnicalIncident] = []
        group_commits: list[tuple[str, str]] = []
        owner: dict[AlarmIdentity, str] = {}
        for snapshot in snapshots:
            document = snapshot.as_document()
            basis = document.get('state_basis')
            if basis != {
                'alarm_configuration_revision': reference.alarm_configuration_revision,
                'tool_registry_revision': reference.confirmed_tool_catalog_revision,
            }:
                raise AlarmDurableRecoveryError(
                    'snapshot revisions differ from EFFECTIVE; explicit adoption recovery required'
                )
            # Los snapshots V1/V2 no ofrecen recuperación completa del lifecycle.
            group = restore_group_lifecycle(snapshot)
            groups.append(group)
            group_commits.append((group.priority_group, snapshot.last_commit_id))
            for alarm in group.alarms:
                prior = owner.setdefault(alarm.alarm_identity, group.priority_group)
                if prior != group.priority_group:
                    raise AlarmDurableRecoveryError('alarm exists in multiple priority groups')
            for incident in snapshot_technical_incidents(snapshot):
                prior = owner.setdefault(incident.alarm_identity, incident.priority_group)
                if prior != incident.priority_group:
                    raise AlarmDurableRecoveryError('incident exists in multiple priority groups')
                if any(
                    alarm.alarm_identity == incident.alarm_identity and alarm.occurrence is not None
                    for alarm in group.alarms
                ):
                    raise AlarmDurableRecoveryError(
                        'technical incident cannot coexist with physical occurrence'
                    )
                incidents.append(incident)
        if len({item.alarm_identity for item in incidents}) != len(incidents):
            raise AlarmDurableRecoveryError('duplicate technical incident identity')
        lifecycle = AlarmLifecycleRuntimeState(
            configuration=configuration,
            groups=tuple(groups),
            technical_incidents=tuple(incidents),
        )
        # Última comprobación de autoridad para evitar publicar una imagen ya obsoleta.
        context.assert_lease_current()
        if self.persistence.read_head() != head:
            raise AlarmDurableRecoveryError('WAL head changed during Runtime recovery')
        return RecoveredAlarmAuthority(
            artifact_ref=reference,
            lifecycle=lifecycle,
            group_commit_ids=tuple(sorted(group_commits)),
        )
