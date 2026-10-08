# Espejo pedagógico de la persistencia de incidentes técnicos en un commit Engine v2.
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ada.alarms.core import (
    TechnicalIncident,
    TechnicalIncidentChange,
    TechnicalIncidentChangeKind,
)
from ada.alarms.persistence.operational.errors import (
    AlarmPersistenceCorruptionError,
    AlarmPersistenceValidationError,
)
from ada.alarms.persistence.operational.models import (
    GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupRuntimeSnapshot,
)
from ada.alarms.persistence.operational.store import AlarmPersistence
from ada.contracts.alarms import AlarmIdentity


# Rehidrata los incidentes de un snapshot sin volver a evaluar errores.
def snapshot_technical_incidents(snapshot: GroupRuntimeSnapshot) -> tuple[TechnicalIncident, ...]:
    if not isinstance(snapshot, GroupRuntimeSnapshot):
        raise TypeError('snapshot must be a GroupRuntimeSnapshot')
    document = snapshot.as_document()
    items = document.get('technical_incidents', {})
    if not isinstance(items, Mapping):
        raise AlarmPersistenceCorruptionError('technical incidents snapshot is invalid')
    try:
        return tuple(
            sorted(
                (TechnicalIncident.from_document(item) for item in items.values()),
                key=lambda incident: incident.alarm_identity,
            )
        )
    except (TypeError, ValueError) as error:
        raise AlarmPersistenceCorruptionError('technical incidents snapshot is invalid') from error


# Solo permite leer el estado observable cuando el WAL y sus snapshots están alineados.
def read_open_technical_incidents(persistence: AlarmPersistence) -> tuple[TechnicalIncident, ...]:
    if not isinstance(persistence, AlarmPersistence):
        raise TypeError('persistence must be an AlarmPersistence')
    head = persistence.read_head()
    if not head.aligned:
        raise AlarmPersistenceCorruptionError('journal must be recovered before reading incidents')
    persistence.read_effective_head()
    # Comprueba que los snapshots no reemplacen la autoridad de la región durable.
    durable_by_group: dict[str, GroupRuntimeSnapshot] = {}
    for entry in persistence.read_durable_records():
        durable_by_group[entry.record.commit.priority_group] = entry.record.snapshot_after
    current_snapshots = persistence.list_snapshots()
    actual_by_group = {snapshot.priority_group: snapshot for snapshot in current_snapshots}
    if actual_by_group != durable_by_group:
        raise AlarmPersistenceCorruptionError('technical incident snapshots differ from durable WAL')
    open_incidents: dict[AlarmIdentity, TechnicalIncident] = {}
    for snapshot in current_snapshots:
        for incident in snapshot_technical_incidents(snapshot):
            if incident.alarm_identity in open_incidents:
                raise AlarmPersistenceCorruptionError('technical incident is present in multiple groups')
            open_incidents[incident.alarm_identity] = incident
    return tuple(open_incidents[key] for key in sorted(open_incidents))


# Integra transiciones de incidentes al commit de grupo y a la misma autoridad WAL.
# Verifica el encadenamiento: un STARTED no puede duplicar un incidente abierto.
def build_technical_incident_commit(
    *,
    commit: EngineCommitMetadata,
    snapshot_after: GroupRuntimeSnapshot,
    previous_snapshot: GroupRuntimeSnapshot | None,
    open_incidents: Sequence[TechnicalIncident],
    changes: Sequence[TechnicalIncidentChange],
    records: Mapping[str, Any] | None = None,
) -> EngineCommitRecord | None:
    if not isinstance(commit, EngineCommitMetadata):
        raise TypeError('commit must be EngineCommitMetadata')
    if not isinstance(snapshot_after, GroupRuntimeSnapshot):
        raise TypeError('snapshot_after must be GroupRuntimeSnapshot')
    if previous_snapshot is not None and not isinstance(previous_snapshot, GroupRuntimeSnapshot):
        raise TypeError('previous_snapshot must be GroupRuntimeSnapshot or None')
    if snapshot_after.priority_group != commit.priority_group:
        raise AlarmPersistenceValidationError('snapshot group does not match commit')
    if previous_snapshot is None:
        if commit.previous_commit_id is not None:
            raise AlarmPersistenceValidationError('initial technical commit must have no previous id')
    elif (
        previous_snapshot.priority_group != commit.priority_group
        or previous_snapshot.last_commit_id != commit.previous_commit_id
    ):
        raise AlarmPersistenceValidationError('previous snapshot does not match commit chain')
    if isinstance(open_incidents, str | bytes) or not isinstance(open_incidents, Sequence):
        raise TypeError('open_incidents must be a sequence')
    if isinstance(changes, str | bytes) or not isinstance(changes, Sequence):
        raise TypeError('changes must be a sequence')
    previous = {
        incident.alarm_identity: incident
        for incident in (
            () if previous_snapshot is None else snapshot_technical_incidents(previous_snapshot)
        )
    }
    target: dict[AlarmIdentity, TechnicalIncident] = {}
    for incident in open_incidents:
        if not isinstance(incident, TechnicalIncident):
            raise TypeError('open_incidents must contain TechnicalIncident values')
        if incident.priority_group != commit.priority_group:
            raise AlarmPersistenceValidationError('incident priority_group does not match commit')
        if incident.alarm_identity in target:
            raise AlarmPersistenceValidationError('open incidents must be unique by alarm')
        target[incident.alarm_identity] = incident
    expected = dict(previous)
    change_ids: set[str] = set()
    for change in changes:
        if not isinstance(change, TechnicalIncidentChange):
            raise TypeError('changes must contain TechnicalIncidentChange values')
        incident = change.incident
        if incident.priority_group != commit.priority_group:
            raise AlarmPersistenceValidationError('incident change belongs to another group')
        if incident.alarm_identity.canonical_key not in commit.affected_alarms:
            raise AlarmPersistenceValidationError('changed incident must be an affected alarm')
        if change.effective_at > datetime.fromisoformat(commit.evaluated_at.replace('Z', '+00:00')):
            raise AlarmPersistenceValidationError('incident transition is newer than commit cycle')
        if change.record_id in change_ids:
            raise AlarmPersistenceValidationError('duplicate technical incident transition')
        change_ids.add(change.record_id)
        old = expected.get(incident.alarm_identity)
        if change.kind is TechnicalIncidentChangeKind.STARTED:
            if old is not None:
                raise AlarmPersistenceValidationError('STARTED cannot replace an open incident')
            expected[incident.alarm_identity] = incident
        elif change.kind is TechnicalIncidentChangeKind.CHANGED:
            if (
                old is None
                or old.incident_id != incident.incident_id
                or old.fingerprint != change.previous_fingerprint
            ):
                raise AlarmPersistenceValidationError('CHANGED must reference existing incident')
            expected[incident.alarm_identity] = incident
        else:
            if old is None or old != incident:
                raise AlarmPersistenceValidationError('RESOLVED must reference existing incident')
            del expected[incident.alarm_identity]
    if expected != target:
        raise AlarmPersistenceValidationError('incident snapshot does not match transitions')
    if not changes and not records:
        return None
    existing = dict(records or {})
    if 'technical_incident_changes' in existing:
        raise AlarmPersistenceValidationError('technical incident changes must be supplied separately')
    if changes:
        existing['technical_incident_changes'] = [change.as_document() for change in changes]
    document = snapshot_after.as_document()
    if 'technical_incidents' in document:
        expected_before = (
            {} if previous_snapshot is None
            else previous_snapshot.as_document().get('technical_incidents', {})
        )
        if document['technical_incidents'] != expected_before:
            raise AlarmPersistenceValidationError('snapshot_after technical incidents differ from prior state')
    document['snapshot_schema_version'] = GROUP_RUNTIME_SNAPSHOT_V2_SCHEMA_VERSION
    document['last_commit_id'] = commit.commit_id
    document['technical_incidents'] = {
        identity.canonical_key: target[identity].as_document() for identity in sorted(target)
    }
    return EngineCommitRecord.create(
        commit=commit,
        snapshot_after=GroupRuntimeSnapshot(document),
        records=existing,
    )
