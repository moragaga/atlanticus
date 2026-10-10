# Espejo pedagógico en español. Misma ejecución y contratos del archivo productivo.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ada.alarms.core import AlarmEvaluation, AlarmStatus
from ada.alarms.persistence.operational import AlarmPersistence
from ada.processes.alarm_runtime.job import AlarmRuntimeIterationResult
from atlanticus.state import AtomicJsonStore

DOCUMENT_TYPE = 'ada_alarm_engine_resolved_current_state'
SCHEMA_VERSION = 1
_LATEST = 'current/latest.json'


# Señala inconsistencias de autoridad, integridad o publicación.
class EngineResolvedCurrentPublicationError(RuntimeError):
    pass


# Contrato mínimo de lease y exclusión para mutaciones seguras.
class ResolvedCurrentContext(Protocol):
    def assert_lease_current(self) -> None: ...

    def fenced_mutation(self): ...


# Calcula un checksum del JSON canónico para la comprobación de integridad.
def _digest(document: dict[str, object]) -> str:
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


# Normaliza todas las fechas del contrato a UTC.
def _utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EngineResolvedCurrentPublicationError('Current timestamp must be timezone-aware')
    if value.utcoffset().total_seconds() != 0:
        raise EngineResolvedCurrentPublicationError('Current timestamp must be UTC')
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


# Conserva el estado y contenido físico sin incluir la hora variable de cada polling.
def _evaluation(value: AlarmEvaluation) -> dict[str, object]:
    evidence = value.evidence_snapshot
    error = value.error
    return {
        'status': value.status.value,
        'evidence': (
            None
            if evidence is None
            else {
                'contract_key': evidence.contract_key,
                'contract_version': evidence.contract_version,
                'payload': dict(evidence.payload),
            }
        ),
        'error': (
            None
            if error is None
            else {
                'origin': error.origin.value,
                'error_key': error.error_key,
                'message': error.message,
                'affected_inputs': [
                    {
                        'reason_key': issue.reason_key,
                        'source_key': issue.source_key,
                        'scope_key': issue.scope_key,
                        'resource_key': issue.resource_key,
                        'fields': list(issue.fields),
                    }
                    for issue in error.affected_inputs
                ],
            }
        ),
    }


# Construye la lectura de Modeler desde el ciclo confirmado, manteniendo evidencia y estado interno.
def build_resolved_current_document(
    *, result: AlarmRuntimeIterationResult, artifact_ref: dict, journal_position: dict
) -> dict[str, object]:
    if result.session is None or result.cycle is None or result.lifecycle is None:
        raise EngineResolvedCurrentPublicationError('Resolved CURRENT requires a completed cycle')
    resolution_key = result.session.configuration.resolution_key
    expected_resolution = {
        'alarm_configuration_revision': resolution_key.alarm_configuration_revision,
        'confirmed_tool_catalog_revision': resolution_key.confirmed_tool_catalog_revision,
    }
    if artifact_ref.get('resolution_key') != expected_resolution:
        raise EngineResolvedCurrentPublicationError('Resolved CURRENT differs from EFFECTIVE')
    evaluations = {item.alarm_identity: item for item in result.cycle.evaluations}
    if len(evaluations) != len(result.cycle.evaluations):
        raise EngineResolvedCurrentPublicationError('Duplicate evaluation identity')
    alarms = []
    identities = set()
    for group in result.lifecycle.groups:
        resolution = group.decision.priority_resolution
        priorities = {} if resolution is None else {
            item.alarm_identity: item for item in resolution.alarms
        }
        for current in group.decision.state.alarms:
            occurrence = current.occurrence
            if occurrence is None:
                continue
            identity = current.alarm_identity
            if identity in identities or identity not in evaluations or identity not in priorities:
                raise EngineResolvedCurrentPublicationError('Open occurrence lacks resolved cycle')
            identities.add(identity)
            evaluation = evaluations[identity]
            if evaluation.status is AlarmStatus.INACTIVE:
                raise EngineResolvedCurrentPublicationError('Open occurrence is evaluated INACTIVE')
            priority = priorities[identity]
            management = current.management_effect
            deactivation = current.deactivation_effect
            hold = current.technical_hold
            directly_managed = bool(
                management is not None
                and management.source_occurrence_id == occurrence.occurrence_id
                and management.effective_at <= result.cycle.cycle_at
                and (
                    management.reappearance_due_at is None
                    or result.cycle.cycle_at < management.reappearance_due_at
                )
            )
            alarms.append(
                {
                    'identity': identity.canonical_key,
                    'priority_group': group.priority_group,
                    'occurrence_id': occurrence.occurrence_id,
                    'episode_id': occurrence.episode_id,
                    'started_at': _utc(occurrence.started_at),
                    'evaluation': _evaluation(evaluation),
                    'priority': {
                        'disposition': priority.disposition.value,
                        'blockers': [
                            blocker.canonical_key for blocker in priority.blocking_alarm_identities
                        ],
                    },
                    'management_cycle': current.management_cycle,
                    'directly_managed': directly_managed,
                    'management_effect': (
                        None
                        if management is None
                        else {
                            'effect_id': management.effect_id,
                            'source_occurrence_id': management.source_occurrence_id,
                            'effective_at': _utc(management.effective_at),
                            'reappearance_due_at': (
                                None
                                if management.reappearance_due_at is None
                                else _utc(management.reappearance_due_at)
                            ),
                        }
                    ),
                    'deactivation_effect': (
                        None
                        if deactivation is None
                        else {
                            'effect_id': deactivation.effect_id,
                            'effective_from': _utc(deactivation.effective_from),
                            'effective_until': _utc(deactivation.effective_until),
                        }
                    ),
                    'technical_hold': (
                        None
                        if hold is None
                        else {'started_at': _utc(hold.started_at), 'due_at': _utc(hold.due_at)}
                    ),
                    'assignments': [
                        {'tool_key': assignment.tool_key, 'assigned_at': _utc(assignment.assigned_at)}
                        for assignment in current.assignments
                    ],
                    'pending_assignments': [
                        {'tool_key': pending.tool_key, 'due_at': _utc(pending.due_at)}
                        for pending in current.pending_assignments
                    ],
                }
            )
    document: dict[str, object] = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'artifact_ref': artifact_ref,
        'journal_position': journal_position,
        'state': {
            'resolution_key': expected_resolution,
            'as_of': _utc(result.cycle.cycle_at),
            'alarms': sorted(alarms, key=lambda item: item['identity']),
        },
    }
    document['sha256'] = _digest(document)
    return document


# Rechaza un documento previo inconsistente, sin sobrescribir silenciosamente corrupción.
def _validate_previous(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != {
        'document_type', 'schema_version', 'artifact_ref', 'journal_position', 'state', 'sha256'
    }:
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT has invalid fields')
    if document['document_type'] != DOCUMENT_TYPE or document['schema_version'] != SCHEMA_VERSION:
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT schema is invalid')
    if (
        not isinstance(document['sha256'], str)
        or document['sha256'] != _digest({key: value for key, value in document.items() if key != 'sha256'})
    ):
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT checksum mismatch')
    state = document['state']
    if not isinstance(state, dict) or set(state) != {'resolution_key', 'as_of', 'alarms'}:
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT state is invalid')
    if not isinstance(state['as_of'], str) or not isinstance(state['alarms'], list):
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT state is invalid')
    if not isinstance(document['artifact_ref'], dict) or not isinstance(document['journal_position'], dict):
        raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT provenance is invalid')
    return document


@dataclass(slots=True)
# Publica únicamente la vista operacional efectiva y evita reescrituras por cambios de reloj.
class AlarmResolvedCurrentPublisher:
    root: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('Resolved CURRENT output root must be an absolute Path')
        if not isinstance(self.source_key, str) or not self.source_key or self.source_key.strip() != self.source_key:
            raise ValueError('Resolved CURRENT source_key must be non-empty normalized text')

    def publish(
        self, *, context: ResolvedCurrentContext, persistence: AlarmPersistence,
        result: AlarmRuntimeIterationResult
    ) -> bool:
        if result.cycle is None or result.lifecycle is None:
            return False
        context.assert_lease_current()
        effective = persistence.read_effective_head()
        head = persistence.read_head()
        if effective is None or not head.aligned or head.durable is None:
            raise EngineResolvedCurrentPublicationError('Resolved CURRENT requires durable EFFECTIVE')
        reference = effective.target_artifact_ref
        if reference.source_key != self.source_key:
            raise EngineResolvedCurrentPublicationError('Resolved CURRENT source differs from EFFECTIVE')
        document = build_resolved_current_document(
            result=result,
            artifact_ref=reference.as_document(),
            journal_position=head.durable.as_document(),
        )
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        with context.fenced_mutation():
            if persistence.read_effective_head() != effective or persistence.read_head() != head:
                raise EngineResolvedCurrentPublicationError('Durable authority changed during CURRENT publication')
            previous = store.read(_LATEST)
            if previous is not None:
                previous = _validate_previous(previous)
                if previous['artifact_ref'].get('source_key') != self.source_key:
                    raise EngineResolvedCurrentPublicationError('Existing resolved CURRENT source differs')
                if previous['state']['as_of'] > document['state']['as_of']:
                    raise EngineResolvedCurrentPublicationError('Resolved CURRENT cannot move backward')
                if (
                    previous['artifact_ref'] == document['artifact_ref']
                    and previous['state']['alarms'] == document['state']['alarms']
                ):
                    return False
            store.replace(_LATEST, document)
        return True
