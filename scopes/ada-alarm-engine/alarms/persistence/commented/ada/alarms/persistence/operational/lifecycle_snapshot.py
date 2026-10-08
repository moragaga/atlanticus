# Contrato de traducción entre estado operacional de Core y snapshot durable V3.
# La función de escritura conserva ocurrencias, episodios, estado técnico y efectos.
# La función de lectura reconstruye modelos de Core y rechaza formatos históricos incompletos.
# Los hechos y el control de autoridad permanecen a cargo del WAL de AlarmPersistence.
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from ada.alarms.core import (
    AlarmEpisode,
    AlarmOccurrence,
    AlarmRuntimeState,
    AlarmStatus,
    DeactivationEffect,
    GroupLifecycleState,
    ManagementEffect,
    PendingToolAssignment,
    RuntimeEvaluationState,
    TechnicalHold,
    TechnicalIncident,
    ToolAssignment,
)
from ada.alarms.persistence.operational.models import (
    GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
    GroupRuntimeSnapshot,
)
from ada.contracts.alarms import AlarmIdentity


def snapshot_group_lifecycle(
    state: GroupLifecycleState,
    *,
    commit_id: str,
    alarm_configuration_revision: str,
    tool_registry_revision: str,
    technical_incidents: Sequence[TechnicalIncident],
) -> GroupRuntimeSnapshot:
    if not isinstance(state, GroupLifecycleState):
        raise TypeError('state must be a GroupLifecycleState')
    if not isinstance(commit_id, str) or not commit_id.strip():
        raise ValueError('commit_id must be non-empty')
    if (
        not isinstance(alarm_configuration_revision, str)
        or not alarm_configuration_revision.strip()
    ):
        raise ValueError('alarm_configuration_revision must be non-empty')
    if not isinstance(tool_registry_revision, str) or not tool_registry_revision.strip():
        raise ValueError('tool_registry_revision must be non-empty')
    if isinstance(technical_incidents, str | bytes) or not isinstance(technical_incidents, Sequence):
        raise TypeError('technical_incidents must be a sequence')
    incidents = {}
    for incident in technical_incidents:
        if not isinstance(incident, TechnicalIncident):
            raise TypeError('technical_incidents must contain TechnicalIncident values')
        if incident.priority_group != state.priority_group:
            raise ValueError('technical incident belongs to another group')
        alarm_key = incident.alarm_identity.canonical_key
        if alarm_key in incidents:
            raise ValueError('technical_incidents must not contain duplicate alarm identities')
        incidents[alarm_key] = incident.as_document()
    episode = state.episode
    document = {
        'snapshot_schema_version': GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION,
        'priority_group': state.priority_group,
        'last_commit_id': commit_id,
        'state_basis': {
            'alarm_configuration_revision': alarm_configuration_revision,
            'tool_registry_revision': tool_registry_revision,
        },
        'episode': (
            None
            if episode is None
            else {'episode_id': episode.episode_id, 'started_at': _ts(episode.started_at)}
        ),
        'alarms': {
            item.alarm_identity.canonical_key: _alarm_document(item, commit_id)
            for item in state.alarms
        },
        'technical_incidents': incidents,
    }
    return GroupRuntimeSnapshot(document)


def restore_group_lifecycle(snapshot: GroupRuntimeSnapshot) -> GroupLifecycleState:
    if not isinstance(snapshot, GroupRuntimeSnapshot):
        raise TypeError('snapshot must be a GroupRuntimeSnapshot')
    doc = snapshot.as_document()
    if doc['snapshot_schema_version'] != GROUP_RUNTIME_SNAPSHOT_V3_SCHEMA_VERSION:
        raise ValueError('lossless lifecycle recovery requires snapshot v3')
    group = doc['priority_group']
    episode_doc = doc.get('episode')
    episode = (
        None
        if episode_doc is None
        else AlarmEpisode(
            episode_id=episode_doc['episode_id'],
            priority_group=group,
            started_at=_dt(episode_doc['started_at']),
        )
    )
    alarms = []
    for alarm_key, state in sorted(doc['alarms'].items()):
        family_key, sep, identity_key = alarm_key.partition('/')
        if not sep or not family_key or not identity_key or '/' in identity_key:
            raise ValueError('snapshot alarm identity is invalid')
        identity = AlarmIdentity(family_key=family_key, alarm_key=identity_key)
        occurrence = state.get('occurrence')
        management = state.get('management_effect')
        deactivation = state.get('deactivation_effect')
        evaluation = None if occurrence is None else occurrence['last_evaluation']
        alarms.append(
            AlarmRuntimeState(
                alarm_identity=identity,
                occurrence=(
                    None
                    if occurrence is None
                    else AlarmOccurrence(
                        occurrence_id=occurrence['occurrence_id'],
                        alarm_identity=identity,
                        episode_id=episode.episode_id if episode is not None else '',
                        started_at=_dt(occurrence['started_at']),
                        alarm_configuration_revision=occurrence['configuration_revision_at_start'],
                        tool_registry_revision=occurrence['tool_registry_revision_at_start'],
                    )
                ),
                last_evaluation=(
                    None
                    if evaluation is None
                    else RuntimeEvaluationState(
                        status=AlarmStatus(evaluation['status']),
                        evaluated_at=_dt(evaluation['evaluated_at']),
                        error_key=evaluation.get('error_key'),
                    )
                ),
                technical_hold=(
                    None
                    if occurrence is None or occurrence.get('technical_hold') is None
                    else TechnicalHold(
                        started_at=_dt(occurrence['technical_hold']['started_at']),
                        due_at=_dt(occurrence['technical_hold']['due_at']),
                    )
                ),
                management_cycle=None if occurrence is None else occurrence['management_cycle'],
                management_effect=(
                    None
                    if management is None
                    else ManagementEffect(
                        effect_id=management['effect_id'],
                        source_occurrence_id=management['source_occurrence_id'],
                        effective_at=_dt(management['effective_at']),
                        reappearance_due_at=(
                            None
                            if management['reappearance_due_at'] is None
                            else _dt(management['reappearance_due_at'])
                        ),
                    )
                ),
                deactivation_effect=(
                    None
                    if deactivation is None
                    else DeactivationEffect(
                        effect_id=deactivation['effect_id'],
                        source_occurrence_id=deactivation['source_occurrence_id'],
                        effective_from=_dt(deactivation['effective_from']),
                        effective_until=_dt(deactivation['effective_until']),
                    )
                ),
                assignments=(
                    ()
                    if occurrence is None
                    else tuple(
                        ToolAssignment(tool_key=tool, assigned_at=_dt(item['assigned_at']))
                        for tool, item in sorted(occurrence['assignments'].items())
                    )
                ),
                pending_assignments=(
                    ()
                    if occurrence is None
                    else tuple(
                        PendingToolAssignment(tool_key=tool, due_at=_dt(item['due_at']))
                        for tool, item in sorted(occurrence['pending_assignments'].items())
                    )
                ),
                next_evidence_due_at=(
                    None
                    if occurrence is None or occurrence.get('next_evidence_due_at') is None
                    else _dt(occurrence['next_evidence_due_at'])
                ),
            )
        )
    return GroupLifecycleState(priority_group=group, episode=episode, alarms=tuple(alarms))


def _alarm_document(state: AlarmRuntimeState, commit_id: str) -> dict:
    occurrence = state.occurrence
    management = state.management_effect
    deactivation = state.deactivation_effect
    return {
        'last_commit_id': commit_id,
        'occurrence': (
            None
            if occurrence is None
            else {
                'occurrence_id': occurrence.occurrence_id,
                'started_at': _ts(occurrence.started_at),
                'configuration_revision_at_start': occurrence.alarm_configuration_revision,
                'tool_registry_revision_at_start': occurrence.tool_registry_revision,
                'last_evaluation': {
                    'status': state.last_evaluation.status.value,
                    'evaluated_at': _ts(state.last_evaluation.evaluated_at),
                    **(
                        {'error_key': state.last_evaluation.error_key}
                        if state.last_evaluation.error_key is not None
                        else {}
                    ),
                },
                'management_cycle': state.management_cycle,
                'assignments': {
                    item.tool_key: {'assigned_at': _ts(item.assigned_at)}
                    for item in state.assignments
                },
                'pending_assignments': {
                    item.tool_key: {'due_at': _ts(item.due_at)}
                    for item in state.pending_assignments
                },
                'technical_hold': (
                    None
                    if state.technical_hold is None
                    else {
                        'started_at': _ts(state.technical_hold.started_at),
                        'due_at': _ts(state.technical_hold.due_at),
                    }
                ),
                'next_evidence_due_at': (
                    None
                    if state.next_evidence_due_at is None
                    else _ts(state.next_evidence_due_at)
                ),
            }
        ),
        'management_effect': (
            None
            if management is None
            else {
                'effect_id': management.effect_id,
                'source_occurrence_id': management.source_occurrence_id,
                'effective_at': _ts(management.effective_at),
                'reappearance_due_at': (
                    None
                    if management.reappearance_due_at is None
                    else _ts(management.reappearance_due_at)
                ),
            }
        ),
        'deactivation_effect': (
            None
            if deactivation is None
            else {
                'effect_id': deactivation.effect_id,
                'source_occurrence_id': deactivation.source_occurrence_id,
                'effective_from': _ts(deactivation.effective_from),
                'effective_until': _ts(deactivation.effective_until),
            }
        ),
    }


def _ts(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError('timestamp must be UTC')
    return value.isoformat().replace('+00:00', 'Z')


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))
