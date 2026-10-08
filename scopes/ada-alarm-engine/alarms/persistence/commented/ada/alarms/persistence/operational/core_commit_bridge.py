# Espejo pedagógico de la preparación de commits integrados de Core.
# No publica WAL ni estado de Runtime: prepara candidatos verificables.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ada.alarms.core import (
    DEFAULT_EVIDENCE_SAMPLING_INTERVAL_SECONDS,
    AlarmEvaluation,
    EvidenceContractRef,
    GroupLifecycleDecision,
    GroupLifecycleState,
    GroupPriorityResolution,
    TechnicalIncident,
    TechnicalIncidentChange,
    TechnicalIncidentChangeKind,
    commit_id_for,
    cycle_id_for,
    materialize_group_commit,
)
from ada.alarms.persistence.operational.lifecycle_snapshot import (
    restore_group_lifecycle,
    snapshot_group_lifecycle,
)
from ada.alarms.persistence.operational.models import (
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
)
from ada.alarms.persistence.operational.technical_incidents import (
    snapshot_technical_incidents,
)
from ada.contracts.alarms import AlarmIdentity


@dataclass(frozen=True, slots=True)
# Resultado inmutable de un grupo, con snapshot validado.
class PreparedGroupCommit:
    record: EngineCommitRecord
    state: GroupLifecycleState
    technical_incidents: tuple[TechnicalIncident, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.record, EngineCommitRecord):
            raise TypeError('record must be an EngineCommitRecord')
        if not isinstance(self.state, GroupLifecycleState):
            raise TypeError('state must be a GroupLifecycleState')
        if self.record.commit.priority_group != self.state.priority_group:
            raise ValueError('prepared state does not match commit group')
        if not isinstance(self.technical_incidents, tuple) or not all(
            isinstance(item, TechnicalIncident) for item in self.technical_incidents
        ):
            raise TypeError('technical_incidents must be TechnicalIncident values')


# Combina hechos físicos y transiciones técnicas en un único commit V3.
# Comprueba la coincidencia exacta del estado previo con el snapshot confirmado.
def prepare_group_commit(
    *,
    previous_snapshot: GroupRuntimeSnapshot | None,
    previous_state: GroupLifecycleState,
    decision: GroupLifecycleDecision,
    evaluations: Sequence[AlarmEvaluation],
    technical_incidents: Sequence[TechnicalIncident],
    technical_incident_changes: Sequence[TechnicalIncidentChange],
    cycle_at: datetime,
    committed_at: datetime,
    alarm_configuration_revision: str,
    tool_registry_revision: str,
    runtime_artifact_version: str,
    evidence_sampling_interval_seconds: int = DEFAULT_EVIDENCE_SAMPLING_INTERVAL_SECONDS,
    technical_evidence_contract: EvidenceContractRef | None = None,
    previous_priority_resolution: GroupPriorityResolution | None = None,
) -> PreparedGroupCommit | None:
    if not isinstance(previous_state, GroupLifecycleState):
        raise TypeError('previous_state must be GroupLifecycleState')
    if not isinstance(decision, GroupLifecycleDecision):
        raise TypeError('decision must be GroupLifecycleDecision')
    group = previous_state.priority_group
    if decision.state.priority_group != group:
        raise ValueError('decision and previous state must share priority_group')
    if not isinstance(cycle_at, datetime) or cycle_at.tzinfo is None:
        raise ValueError('cycle_at must be UTC datetime')
    if not isinstance(committed_at, datetime) or committed_at.tzinfo is None:
        raise ValueError('committed_at must be UTC datetime')
    if cycle_at.utcoffset() != UTC.utcoffset(cycle_at) or committed_at.utcoffset() != UTC.utcoffset(committed_at):
        raise ValueError('commit timestamps must be UTC')
    if committed_at < cycle_at:
        raise ValueError('committed_at must not precede cycle_at')
    if isinstance(evaluations, str | bytes) or not isinstance(evaluations, Sequence):
        raise TypeError('evaluations must be a sequence')
    if any(not isinstance(item, AlarmEvaluation) for item in evaluations):
        raise TypeError('evaluations must contain AlarmEvaluation values')
    if isinstance(technical_incidents, str | bytes) or not isinstance(technical_incidents, Sequence):
        raise TypeError('technical_incidents must be a sequence')
    if isinstance(technical_incident_changes, str | bytes) or not isinstance(technical_incident_changes, Sequence):
        raise TypeError('technical_incident_changes must be a sequence')
    previous_id = None if previous_snapshot is None else previous_snapshot.last_commit_id
    if previous_snapshot is None:
        if previous_state.episode is not None or previous_state.alarms:
            raise ValueError('initial commit requires an empty previous lifecycle state')
        old_incidents: tuple[TechnicalIncident, ...] = ()
    else:
        if previous_snapshot.priority_group != group:
            raise ValueError('previous snapshot belongs to another group')
        if restore_group_lifecycle(previous_snapshot) != previous_state:
            raise ValueError('previous lifecycle state differs from durable snapshot')
        old_incidents = snapshot_technical_incidents(previous_snapshot)
    new_incidents = _validate_incident_transition(
        group=group,
        previous=old_incidents,
        current=technical_incidents,
        changes=technical_incident_changes,
        cycle_at=cycle_at,
    )
    materialized = materialize_group_commit(
        previous_state,
        decision,
        evaluations=evaluations,
        cycle_at=cycle_at,
        committed_at=committed_at,
        alarm_configuration_revision=alarm_configuration_revision,
        tool_registry_revision=tool_registry_revision,
        runtime_artifact_version=runtime_artifact_version,
        previous_commit_id=previous_id,
        evidence_sampling_interval_seconds=evidence_sampling_interval_seconds,
        technical_evidence_contract=technical_evidence_contract,
        previous_priority_resolution=previous_priority_resolution,
    )
    if materialized is None and not technical_incident_changes:
        return None
    state = decision.state if materialized is None else materialized.state
    affected = {
        item.incident.alarm_identity.canonical_key for item in technical_incident_changes
    }
    records: dict = {}
    if materialized is not None:
        affected.update(item.canonical_key for item in materialized.commit.affected_alarms)
        records.update(materialized.records.as_document())
    if technical_incident_changes:
        records['technical_incident_changes'] = [
            item.as_document() for item in technical_incident_changes
        ]
    for incident in new_incidents:
        if any(alarm.alarm_identity == incident.alarm_identity and alarm.occurrence is not None for alarm in state.alarms):
            raise ValueError('technical incident cannot coexist with an open physical occurrence')
    commit_id = commit_id_for(cycle_id_for(cycle_at), group)
    metadata = EngineCommitMetadata(
        commit_id=commit_id,
        cycle_id=cycle_id_for(cycle_at),
        priority_group=group,
        previous_commit_id=previous_id,
        evaluated_at=_timestamp(cycle_at),
        committed_at=_timestamp(committed_at),
        alarm_configuration_revision=alarm_configuration_revision,
        tool_registry_revision=tool_registry_revision,
        runtime_artifact_version=runtime_artifact_version,
        affected_alarms=tuple(sorted(affected)),
    )
    snapshot = snapshot_group_lifecycle(
        state,
        commit_id=commit_id,
        alarm_configuration_revision=alarm_configuration_revision,
        tool_registry_revision=tool_registry_revision,
        technical_incidents=new_incidents,
    )
    record = EngineCommitRecord.create(
        commit=metadata,
        snapshot_after=snapshot,
        records=records,
    )
    return PreparedGroupCommit(record=record, state=state, technical_incidents=new_incidents)


# Reconstruye incidentes esperados y rechaza saltos, duplicados o cambios de grupo.
def _validate_incident_transition(
    *,
    group: str,
    previous: Sequence[TechnicalIncident],
    current: Sequence[TechnicalIncident],
    changes: Sequence[TechnicalIncidentChange],
    cycle_at: datetime,
) -> tuple[TechnicalIncident, ...]:
    prior = {item.alarm_identity: item for item in previous}
    if len(prior) != len(previous):
        raise ValueError('previous technical incidents must be unique')
    expected = dict(prior)
    seen: set[AlarmIdentity] = set()
    for change in changes:
        if not isinstance(change, TechnicalIncidentChange):
            raise TypeError('technical_incident_changes must contain TechnicalIncidentChange values')
        incident = change.incident
        identity = incident.alarm_identity
        if incident.priority_group != group:
            raise ValueError('technical incident change belongs to another group')
        if change.effective_at > cycle_at:
            raise ValueError('technical incident change exceeds cycle_at')
        if identity in seen:
            raise ValueError('multiple technical incident transitions for the same alarm')
        seen.add(identity)
        old = expected.get(identity)
        if change.kind is TechnicalIncidentChangeKind.STARTED:
            if old is not None:
                raise ValueError('technical incident already open')
            expected[identity] = incident
        elif change.kind is TechnicalIncidentChangeKind.CHANGED:
            if old is None or old.incident_id != incident.incident_id or old.fingerprint != change.previous_fingerprint:
                raise ValueError('technical incident CHANGED does not match prior state')
            expected[identity] = incident
        elif change.kind is TechnicalIncidentChangeKind.RESOLVED:
            if old != incident:
                raise ValueError('technical incident RESOLVED does not match prior state')
            del expected[identity]
        else:
            raise ValueError('unsupported technical incident transition')
    target: dict[AlarmIdentity, TechnicalIncident] = {}
    for incident in current:
        if not isinstance(incident, TechnicalIncident):
            raise TypeError('technical_incidents must contain TechnicalIncident values')
        if incident.priority_group != group:
            raise ValueError('technical incident belongs to another group')
        if incident.alarm_identity in target:
            raise ValueError('technical incidents must be unique by alarm identity')
        target[incident.alarm_identity] = incident
    if expected != target:
        raise ValueError('technical incident transitions do not reconstruct target state')
    return tuple(target[key] for key in sorted(target))


# Representación UTC usada por la metadata del WAL.
def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')
