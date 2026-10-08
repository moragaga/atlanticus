from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping, Sequence

from ada.alarms.core.models import (
    AffectedInputIssue,
    AlarmEvaluation,
    AlarmStatus,
    EvaluationError,
    EvaluationErrorOrigin,
)
from ada.contracts.alarms import AlarmIdentity

TECHNICAL_INCIDENT_SCHEMA_VERSION = 'technical-incident.v1'
TECHNICAL_INCIDENT_CHANGE_SCHEMA_VERSION = 'technical-incident-change.v1'


class TechnicalIncidentChangeKind(StrEnum):
    STARTED = 'STARTED'
    CHANGED = 'CHANGED'
    RESOLVED = 'RESOLVED'


class TechnicalIncidentResolution(StrEnum):
    VALID_EVALUATION = 'VALID_EVALUATION'
    CONFIGURATION_WITHDRAWN = 'CONFIGURATION_WITHDRAWN'


@dataclass(frozen=True, slots=True)
class TechnicalIncident:
    incident_id: str
    alarm_identity: AlarmIdentity
    priority_group: str
    started_at: datetime
    changed_at: datetime
    error: EvaluationError
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.alarm_identity, AlarmIdentity):
            raise TypeError('alarm_identity must be an AlarmIdentity')
        if not isinstance(self.priority_group, str) or not self.priority_group.strip():
            raise ValueError('priority_group must be non-empty text')
        _require_utc(self.started_at, 'started_at')
        _require_utc(self.changed_at, 'changed_at')
        if self.changed_at < self.started_at:
            raise ValueError('changed_at must not precede started_at')
        if not isinstance(self.error, EvaluationError):
            raise TypeError('error must be an EvaluationError')
        if self.incident_id != _incident_id(self.alarm_identity, self.started_at):
            raise ValueError('incident_id does not match incident identity')
        if self.fingerprint != technical_error_fingerprint(self.alarm_identity, self.error):
            raise ValueError('fingerprint does not match technical error')

    def as_document(self) -> dict[str, Any]:
        return {
            'schema_version': TECHNICAL_INCIDENT_SCHEMA_VERSION,
            'incident_id': self.incident_id,
            'alarm_identity': _identity_document(self.alarm_identity),
            'priority_group': self.priority_group,
            'started_at': _timestamp(self.started_at),
            'changed_at': _timestamp(self.changed_at),
            'error': _error_document(self.error),
            'fingerprint': self.fingerprint,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> TechnicalIncident:
        _exact_keys(
            document,
            {
                'schema_version',
                'incident_id',
                'alarm_identity',
                'priority_group',
                'started_at',
                'changed_at',
                'error',
                'fingerprint',
            },
            'technical incident',
        )
        if document['schema_version'] != TECHNICAL_INCIDENT_SCHEMA_VERSION:
            raise ValueError('technical incident schema version is unsupported')
        return cls(
            incident_id=document['incident_id'],
            alarm_identity=_identity_from_document(document['alarm_identity']),
            priority_group=document['priority_group'],
            started_at=_parse_timestamp(document['started_at']),
            changed_at=_parse_timestamp(document['changed_at']),
            error=_error_from_document(document['error']),
            fingerprint=document['fingerprint'],
        )


@dataclass(frozen=True, slots=True)
class TechnicalIncidentChange:
    kind: TechnicalIncidentChangeKind
    incident: TechnicalIncident
    effective_at: datetime
    previous_fingerprint: str | None = None
    resolution: TechnicalIncidentResolution | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TechnicalIncidentChangeKind):
            raise TypeError('kind must be a TechnicalIncidentChangeKind')
        if not isinstance(self.incident, TechnicalIncident):
            raise TypeError('incident must be a TechnicalIncident')
        _require_utc(self.effective_at, 'effective_at')
        if self.effective_at < self.incident.started_at:
            raise ValueError('change cannot precede incident start')
        if self.kind is TechnicalIncidentChangeKind.STARTED:
            if self.previous_fingerprint is not None or self.resolution is not None:
                raise ValueError('STARTED must not have previous_fingerprint or resolution')
            if self.effective_at != self.incident.started_at:
                raise ValueError('STARTED must match incident start')
        elif self.kind is TechnicalIncidentChangeKind.CHANGED:
            if not isinstance(self.previous_fingerprint, str) or not self.previous_fingerprint:
                raise ValueError('CHANGED requires previous_fingerprint')
            if (
                self.previous_fingerprint == self.incident.fingerprint
                or self.resolution is not None
            ):
                raise ValueError('CHANGED requires a different fingerprint without resolution')
            if self.effective_at != self.incident.changed_at:
                raise ValueError('CHANGED must match incident changed_at')
        else:
            if not isinstance(self.resolution, TechnicalIncidentResolution):
                raise ValueError('RESOLVED requires resolution')
            if self.previous_fingerprint is not None:
                raise ValueError('RESOLVED must not have previous_fingerprint')

    @property
    def record_id(self) -> str:
        material = (
            self.incident.incident_id,
            self.kind.value,
            _timestamp(self.effective_at),
            self.previous_fingerprint,
            self.incident.fingerprint,
            None if self.resolution is None else self.resolution.value,
        )
        return 'technical-incident-change:' + _digest(material)

    def as_document(self) -> dict[str, Any]:
        return {
            'schema_version': TECHNICAL_INCIDENT_CHANGE_SCHEMA_VERSION,
            'record_id': self.record_id,
            'kind': self.kind.value,
            'incident_id': self.incident.incident_id,
            'alarm_key': self.incident.alarm_identity.canonical_key,
            'priority_group': self.incident.priority_group,
            'effective_at': _timestamp(self.effective_at),
            'previous_fingerprint': self.previous_fingerprint,
            'fingerprint': self.incident.fingerprint,
            'resolution': None if self.resolution is None else self.resolution.value,
            'error': _error_document(self.incident.error),
        }


@dataclass(frozen=True, slots=True)
class TechnicalIncidentReduction:
    open_incidents: tuple[TechnicalIncident, ...]
    changes: tuple[TechnicalIncidentChange, ...]


def technical_error_fingerprint(identity: AlarmIdentity, error: EvaluationError) -> str:
    if not isinstance(identity, AlarmIdentity):
        raise TypeError('identity must be an AlarmIdentity')
    if not isinstance(error, EvaluationError):
        raise TypeError('error must be an EvaluationError')
    return 'sha256:' + _digest(
        {
            'alarm_key': identity.canonical_key,
            'origin': error.origin.value,
            'error_key': error.error_key,
            'affected_inputs': _normalized_issues(error.affected_inputs),
        }
    )


def reduce_initial_technical_incidents(
    previous: Sequence[TechnicalIncident],
    *,
    evaluations: Sequence[AlarmEvaluation],
    executable_groups: Mapping[AlarmIdentity, str],
    physical_occurrences: frozenset[AlarmIdentity] = frozenset(),
    cycle_at: datetime,
) -> TechnicalIncidentReduction:
    _require_utc(cycle_at, 'cycle_at')
    if not isinstance(executable_groups, Mapping):
        raise TypeError('executable_groups must be a mapping')
    if not isinstance(physical_occurrences, frozenset):
        raise TypeError('physical_occurrences must be a frozenset')
    active: dict[AlarmIdentity, TechnicalIncident] = {}
    for incident in previous:
        if not isinstance(incident, TechnicalIncident):
            raise TypeError('previous must contain TechnicalIncident values')
        if incident.alarm_identity in active:
            raise ValueError('previous incidents must be unique by alarm identity')
        active[incident.alarm_identity] = incident
    evaluated: set[AlarmIdentity] = set()
    changes: list[TechnicalIncidentChange] = []
    for evaluation in sorted(evaluations, key=lambda item: item.alarm_identity):
        if not isinstance(evaluation, AlarmEvaluation):
            raise TypeError('evaluations must contain AlarmEvaluation values')
        identity = evaluation.alarm_identity
        if identity in evaluated:
            raise ValueError('evaluations must be unique by alarm identity')
        evaluated.add(identity)
        if evaluation.evaluated_at != cycle_at:
            raise ValueError('evaluation timestamp must match cycle_at')
        group = executable_groups.get(identity)
        if group is None:
            raise ValueError('evaluation alarm is not executable')
        prior = active.get(identity)
        if prior is not None and prior.priority_group != group:
            raise ValueError('priority_group cannot change for an open incident')
        if evaluation.status is AlarmStatus.ERROR:
            if identity in physical_occurrences:
                continue
            error = evaluation.error
            if error is None:
                raise ValueError('ERROR evaluation requires error')
            fingerprint = technical_error_fingerprint(identity, error)
            if prior is None:
                incident = TechnicalIncident(
                    incident_id=_incident_id(identity, cycle_at),
                    alarm_identity=identity,
                    priority_group=group,
                    started_at=cycle_at,
                    changed_at=cycle_at,
                    error=error,
                    fingerprint=fingerprint,
                )
                active[identity] = incident
                changes.append(
                    TechnicalIncidentChange(
                        kind=TechnicalIncidentChangeKind.STARTED,
                        incident=incident,
                        effective_at=cycle_at,
                    )
                )
            elif prior.fingerprint != fingerprint:
                incident = TechnicalIncident(
                    incident_id=prior.incident_id,
                    alarm_identity=identity,
                    priority_group=group,
                    started_at=prior.started_at,
                    changed_at=cycle_at,
                    error=error,
                    fingerprint=fingerprint,
                )
                active[identity] = incident
                changes.append(
                    TechnicalIncidentChange(
                        kind=TechnicalIncidentChangeKind.CHANGED,
                        incident=incident,
                        effective_at=cycle_at,
                        previous_fingerprint=prior.fingerprint,
                    )
                )
            continue
        if prior is not None:
            changes.append(
                TechnicalIncidentChange(
                    kind=TechnicalIncidentChangeKind.RESOLVED,
                    incident=prior,
                    effective_at=cycle_at,
                    resolution=TechnicalIncidentResolution.VALID_EVALUATION,
                )
            )
            del active[identity]
    for identity in sorted(set(active) - set(executable_groups)):
        incident = active.pop(identity)
        changes.append(
            TechnicalIncidentChange(
                kind=TechnicalIncidentChangeKind.RESOLVED,
                incident=incident,
                effective_at=cycle_at,
                resolution=TechnicalIncidentResolution.CONFIGURATION_WITHDRAWN,
            )
        )
    return TechnicalIncidentReduction(
        open_incidents=tuple(active[key] for key in sorted(active)),
        changes=tuple(
            sorted(changes, key=lambda item: (item.effective_at, item.incident.alarm_identity))
        ),
    )


def _incident_id(identity: AlarmIdentity, started_at: datetime) -> str:
    return 'technical-incident:' + _digest((identity.canonical_key, _timestamp(started_at)))


def _normalized_issues(issues: tuple[AffectedInputIssue, ...]) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                'reason_key': issue.reason_key,
                'source_key': issue.source_key,
                'scope_key': issue.scope_key,
                'resource_key': issue.resource_key,
                'fields': sorted(issue.fields),
            }
            for issue in issues
        ),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(',', ':')),
    )


def _error_document(error: EvaluationError) -> dict[str, Any]:
    return {
        'origin': error.origin.value,
        'error_key': error.error_key,
        'message': error.message,
        'affected_inputs': _normalized_issues(error.affected_inputs),
    }


def _error_from_document(value: Any) -> EvaluationError:
    _exact_keys(value, {'origin', 'error_key', 'message', 'affected_inputs'}, 'error')
    issues = value['affected_inputs']
    if not isinstance(issues, list):
        raise ValueError('error affected_inputs must be an array')
    normalized = []
    for item in issues:
        _exact_keys(
            item, {'reason_key', 'source_key', 'scope_key', 'resource_key', 'fields'}, 'issue'
        )
        fields = item['fields']
        if not isinstance(fields, list):
            raise ValueError('issue fields must be an array')
        normalized.append(
            AffectedInputIssue(
                reason_key=item['reason_key'],
                source_key=item['source_key'],
                scope_key=item['scope_key'],
                resource_key=item['resource_key'],
                fields=tuple(fields),
            )
        )
    return EvaluationError(
        origin=EvaluationErrorOrigin(value['origin']),
        error_key=value['error_key'],
        message=value['message'],
        affected_inputs=tuple(normalized),
    )


def _identity_document(identity: AlarmIdentity) -> dict[str, str]:
    return {'family_key': identity.family_key, 'alarm_key': identity.alarm_key}


def _identity_from_document(value: Any) -> AlarmIdentity:
    _exact_keys(value, {'family_key', 'alarm_key'}, 'alarm identity')
    return AlarmIdentity(family_key=value['family_key'], alarm_key=value['alarm_key'])


def _exact_keys(document: Any, expected: set[str], label: str) -> None:
    if not isinstance(document, Mapping) or set(document) != expected:
        raise ValueError(f'{label} document has unexpected or missing fields')


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def _timestamp(value: datetime) -> str:
    _require_utc(value, 'timestamp')
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('timestamp must be a UTC ISO-8601 value')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('timestamp must be a UTC ISO-8601 value') from error
    _require_utc(parsed, 'timestamp')
    if _timestamp(parsed) != value:
        raise ValueError('timestamp must be canonical')
    return parsed


def _require_utc(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f'{name} must be a timezone-aware UTC datetime')
