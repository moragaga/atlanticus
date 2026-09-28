# Produce el snapshot CURRENT completo después de confirmar los cambios durables.
# No almacena encuestas repetidas de INACTIVE ni decide qué alarms se muestran.
# La evidencia es la evaluación del ciclo actual y no el último muestreo histórico.
# El store reemplaza atómicamente únicamente la versión CURRENT.

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ada_command_center.alarms.persistence import AlarmArtifactRefSnapshot
from atlanticus.state import AtomicJsonStore

DOCUMENT_TYPE = 'ada_command_center_engine_resolved_current_state'
SCHEMA_VERSION = 1
_LATEST = 'current/latest.json'


class EngineCurrentPublicationError(RuntimeError):
    pass


def _utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Current state timestamps must be timezone-aware UTC')
    if value.utcoffset().total_seconds() != 0:
        raise ValueError('Current state timestamps must be UTC')
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _identity(identity) -> str:
    return identity.canonical_key


def _evaluation(value) -> dict[str, object]:
    snapshot = value.evidence_snapshot
    error = value.error
    return {
        'status': value.status.value,
        'evaluated_at': _utc(value.evaluated_at),
        'evidence': (
            None
            if snapshot is None
            else {
                'contract_key': snapshot.contract_key,
                'contract_version': snapshot.contract_version,
                'payload': dict(snapshot.payload),
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


def build_current_document(*, result, pin: AlarmArtifactRefSnapshot, inputs) -> dict[str, object]:
    evaluations = {value.alarm_identity: value for value in result.evaluations}
    alarms = []
    seen = set()
    for group in result.groups:
        resolution = group.decision.priority_resolution
        priorities = (
            {}
            if resolution is None
            else {entry.alarm_identity: entry for entry in resolution.alarms}
        )
        for runtime in group.decision.state.alarms:
            occurrence = runtime.occurrence
            if occurrence is None:
                continue
            identity = runtime.alarm_identity
            if identity in seen or identity not in priorities or identity not in evaluations:
                raise EngineCurrentPublicationError(
                    'Open occurrence lacks unique resolved cycle data'
                )
            seen.add(identity)
            priority = priorities[identity]
            pending = [
                item.request
                for item in inputs.pending_deactivation_requests
                if item.request.alarm_identity == identity
                and item.request.source_occurrence_id == occurrence.occurrence_id
            ]
            if len(pending) > 1:
                raise EngineCurrentPublicationError(
                    'Multiple pending requests target one occurrence'
                )
            management = runtime.management_effect
            deactivation = runtime.deactivation_effect
            hold = runtime.technical_hold
            alarms.append(
                {
                    'identity': _identity(identity),
                    'occurrence_id': occurrence.occurrence_id,
                    'episode_id': occurrence.episode_id,
                    'started_at': _utc(occurrence.started_at),
                    'evaluation': _evaluation(evaluations[identity]),
                    'priority': {
                        'disposition': priority.disposition.value,
                        'blockers': [
                            _identity(value) for value in priority.blocking_alarm_identities
                        ],
                    },
                    'technical_hold': (
                        None
                        if hold is None
                        else {'started_at': _utc(hold.started_at), 'due_at': _utc(hold.due_at)}
                    ),
                    'management_cycle': runtime.management_cycle,
                    'management_effect': (
                        None
                        if management is None
                        else {
                            'effect_id': management.effect_id,
                            'effective_at': _utc(management.effective_at),
                            'reappearance_due_at': _utc(management.reappearance_due_at),
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
                    'pending_deactivation_request': (
                        None
                        if not pending
                        else {
                            'request_id': pending[0].request_id,
                            'requested_at': _utc(pending[0].requested_at),
                            'effective_until': _utc(pending[0].effective_until),
                        }
                    ),
                    'assignments': [
                        {'tool_key': item.tool_key, 'assigned_at': _utc(item.assigned_at)}
                        for item in runtime.assignments
                    ],
                    'pending_assignments': [
                        {'tool_key': item.tool_key, 'due_at': _utc(item.due_at)}
                        for item in runtime.pending_assignments
                    ],
                }
            )
    state = {
        'resolution_key': pin.as_document()['resolution_key'],
        'as_of': _utc(result.iteration.as_of),
        'alarms': sorted(alarms, key=lambda value: value['identity']),
    }
    document = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'artifact_ref': pin.as_document(),
        'state': state,
    }
    digest = hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()
    document['sha256'] = digest
    return document


@dataclass(slots=True)
class AlarmCurrentStatePublisher:
    root: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('Engine output root must be an absolute Path')
        if not isinstance(self.source_key, str) or not self.source_key.strip():
            raise ValueError('Engine output source_key must be non-empty text')

    def publish(self, *, context, result, pin: AlarmArtifactRefSnapshot, inputs) -> bool:
        if not isinstance(pin, AlarmArtifactRefSnapshot) or pin.source_key != self.source_key:
            raise EngineCurrentPublicationError('Current state source differs from EFFECTIVE')
        state = build_current_document(result=result, pin=pin, inputs=inputs)
        store = AtomicJsonStore(root_path=self.root, max_document_bytes=None)
        context.assert_lease_current()
        with context.fenced_mutation():
            previous = store.read(_LATEST)
            if previous is not None:
                _require_existing_state(previous)
                previous_at = previous['state']['as_of']
                next_at = state['state']['as_of']
                if previous_at > next_at:
                    raise EngineCurrentPublicationError('Current state must not move backward')
                if previous_at == next_at:
                    if previous != state:
                        raise EngineCurrentPublicationError(
                            'Conflicting current states share as_of'
                        )
                    return False
            store.replace(_LATEST, state)
        return True


def _require_existing_state(document: Mapping[str, object]) -> None:
    if (
        document.get('document_type') != DOCUMENT_TYPE
        or document.get('schema_version') != SCHEMA_VERSION
        or not isinstance(document.get('state'), Mapping)
        or not isinstance(document['state'].get('as_of'), str)
        or not isinstance(document.get('sha256'), str)
    ):
        raise EngineCurrentPublicationError('Existing current state is invalid')
    payload = {key: value for key, value in document.items() if key != 'sha256'}
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()
    if document['sha256'] != digest:
        raise EngineCurrentPublicationError('Existing current state integrity check failed')
