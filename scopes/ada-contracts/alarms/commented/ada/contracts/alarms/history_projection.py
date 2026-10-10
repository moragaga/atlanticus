from __future__ import annotations

# Espejo pedagógico del contrato puro de proyección FACTS v4.
# No persiste Parquet, no modifica WAL/FACTS y no avanza el checkpoint del Historian.
# Cada colección tiene un destino definido o una exclusión explícitamente visible.

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ada.contracts.alarms.facts_stream import CommittedFacts


# Un fallo de mapeo no debe producir pérdidas silenciosas de hechos históricos.
class AlarmHistoryProjectionError(ValueError):
    pass


# Seis historias de consulta diferentes, no seis nuevas fuentes de autoridad.
class AlarmHistoryDomain(StrEnum):
    LIFECYCLE = 'lifecycle'
    MANAGEMENT = 'management'
    CASCADE = 'cascade'
    EVIDENCE = 'evidence'
    DEACTIVATION = 'deactivation'
    VISIBILITY = 'visibility'


@dataclass(frozen=True, slots=True)
# Cada fila conserva procedencia, timestamp real y contenido de origen.
class ProjectedAlarmHistoryFact:
    domain: AlarmHistoryDomain
    historian_fact_id: str
    event_kind: str
    event_at_utc: datetime
    day_utc: date
    alarm_key: str | None
    occurrence_id: str | None
    episode_id: str | None
    priority_group: str
    source_stream_id: str
    source_commit_id: str
    source_journal_segment_id: str
    source_journal_byte_offset: int
    source_collection: str
    source_ordinal: int
    source_facts_sha256: str
    timestamp_provenance: str
    payload_json: str


@dataclass(frozen=True, slots=True)
# Una exclusión deliberada es auditable y no se confunde con un hecho procesado.
class ExcludedAlarmHistoryFact:
    collection: str
    ordinal: int
    reason: str


@dataclass(frozen=True, slots=True)
# La salida incluye los hechos materializables y las exclusiones justificadas.
class AlarmHistoryProjection:
    facts: tuple[ProjectedAlarmHistoryFact, ...]
    excluded: tuple[ExcludedAlarmHistoryFact, ...]


_COLLECTION_DOMAINS = {
    'occurrence_changes': AlarmHistoryDomain.LIFECYCLE,
    'episode_changes': AlarmHistoryDomain.LIFECYCLE,
    'management_effects': AlarmHistoryDomain.MANAGEMENT,
    'evidence_records': AlarmHistoryDomain.EVIDENCE,
    'deactivation_requests': AlarmHistoryDomain.DEACTIVATION,
    'deactivation_effects': AlarmHistoryDomain.DEACTIVATION,
    'assignment_changes': AlarmHistoryDomain.VISIBILITY,
}
_EXCLUDED_COLLECTIONS = {
    'configuration_rebases': 'Configuration control is not a v1 historical destination',
    'technical_incident_changes': 'Technical incidents are outside v1 historical destinations',
}
_DUPLICATE_JOURNEY_KEYS = {
    'occurrence_started',
    'occurrence_closed',
    'management_applied',
    'management_response_recorded',
    'management_late',
    'technical_hold_started',
    'technical_hold_expired',
    'technical_hold_recovered',
    'tool_assigned',
    'tool_assignment_removed',
    'tool_assignment_scheduled',
    'tool_assignment_rescheduled',
    'deactivation_expired',
    'deactivation_cleared',
}
_CASCADE_JOURNEY_KEYS = {
    'cascade_suppression_started',
    'cascade_suppression_ended',
    'priority_suppressed',
    'priority_released',
}
_TIMESTAMPS = {
    'occurrence_changes': 'started_at',
    'episode_changes': 'started_at',
    'management_effects': 'effective_at',
    'evidence_records': 'recorded_at',
    'deactivation_requests': 'requested_at',
    'deactivation_effects': 'effective_at',
    'assignment_changes': 'effective_at',
    'journey_events': 'effective_at',
}


# Transforma un commit FACTS verificado sin escribir en ningún sistema externo.
def project_committed_alarm_facts(
    *, facts: CommittedFacts, stream_id: str
) -> AlarmHistoryProjection:
    if not isinstance(stream_id, str) or not stream_id or stream_id != stream_id.strip():
        raise AlarmHistoryProjectionError('stream_id must be non-empty normalized text')
    try:
        commit_id = _nonempty(facts.commit['commit_id'], 'commit_id')
        priority_group = _nonempty(facts.commit['priority_group'], 'priority_group')
        journal_id = _nonempty(facts.journal_position['segment_id'], 'segment_id')
        journal_offset = facts.journal_position['byte_offset']
        digest = _nonempty(facts.position.record_sha256, 'record_sha256')
        records = facts.records
    except (AttributeError, KeyError, TypeError) as error:
        raise AlarmHistoryProjectionError('Invalid committed FACTS envelope') from error
    if (
        not isinstance(journal_offset, int)
        or isinstance(journal_offset, bool)
        or journal_offset <= 0
        or re.fullmatch(r'[0-9a-f]{64}', digest) is None
        or not isinstance(records, dict)
    ):
        raise AlarmHistoryProjectionError('Invalid committed FACTS metadata')
    projected: list[ProjectedAlarmHistoryFact] = []
    excluded: list[ExcludedAlarmHistoryFact] = []
    for collection in sorted(records):
        entries = records[collection]
        if not isinstance(entries, list) or not entries:
            raise AlarmHistoryProjectionError('FACTS collections must contain non-empty lists')
        if collection not in {*_COLLECTION_DOMAINS, *_EXCLUDED_COLLECTIONS, 'journey_events', 'input_receipts'}:
            raise AlarmHistoryProjectionError(f'Unsupported FACTS collection: {collection}')
        for ordinal, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise AlarmHistoryProjectionError('FACTS entries must be objects')
            domain, exclusion = _route(collection, entry)
            if exclusion is not None:
                excluded.append(ExcludedAlarmHistoryFact(collection, ordinal, exclusion))
                continue
            if domain is None:
                raise AlarmHistoryProjectionError('Missing history destination')
            _validate_history_identity(collection, entry)
            timestamp_field = _timestamp_field(collection, entry)
            event_at = _utc_timestamp(entry.get(timestamp_field))
            event_kind = _event_kind(collection, entry)
            source = json.dumps(
                (stream_id, journal_id, journal_offset, commit_id, collection, ordinal),
                ensure_ascii=False,
                separators=(',', ':'),
            ).encode('utf-8')
            payload = json.dumps(
                entry, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False
            )
            projected.append(
                ProjectedAlarmHistoryFact(
                    domain=domain,
                    historian_fact_id=hashlib.sha256(source).hexdigest(),
                    event_kind=event_kind,
                    event_at_utc=event_at,
                    day_utc=event_at.date(),
                    alarm_key=_optional_string(entry, 'alarm_key'),
                    occurrence_id=_optional_string(entry, 'occurrence_id')
                    or _optional_string(entry, 'source_occurrence_id'),
                    episode_id=_optional_string(entry, 'episode_id'),
                    priority_group=priority_group,
                    source_stream_id=stream_id,
                    source_commit_id=commit_id,
                    source_journal_segment_id=journal_id,
                    source_journal_byte_offset=journal_offset,
                    source_collection=collection,
                    source_ordinal=ordinal,
                    source_facts_sha256=digest,
                    timestamp_provenance=(
                        'RECEIPT_APPLIED_AT' if collection == 'input_receipts'
                        and timestamp_field == 'applied_at' else 'SOURCE_EVENT_AT'
                    ),
                    payload_json=payload,
                )
            )
    return AlarmHistoryProjection(tuple(projected), tuple(excluded))


# Evita reinterpretar Journey como historia duplicada de gestión o asignación.
def _route(collection: str, entry: dict[str, Any]) -> tuple[AlarmHistoryDomain | None, str | None]:
    if collection in _EXCLUDED_COLLECTIONS:
        return None, _EXCLUDED_COLLECTIONS[collection]
    if collection in _COLLECTION_DOMAINS:
        return _COLLECTION_DOMAINS[collection], None
    if collection == 'input_receipts':
        kind = entry.get('input_kind')
        if kind == 'MANAGEMENT':
            return AlarmHistoryDomain.MANAGEMENT, None
        if kind in {'DEACTIVATION_REQUEST', 'DEACTIVATION_DECISION'}:
            return AlarmHistoryDomain.DEACTIVATION, None
        raise AlarmHistoryProjectionError('Unknown input receipt kind')
    key = entry.get('event_key')
    if not isinstance(key, str) or not key:
        raise AlarmHistoryProjectionError('Journey event_key is missing')
    if key in _CASCADE_JOURNEY_KEYS:
        if key.startswith('cascade_suppression_'):
            _validate_causal_cascade(entry)
        return AlarmHistoryDomain.CASCADE, None
    if key == 'reappeared':
        return AlarmHistoryDomain.MANAGEMENT, None
    if key in _DUPLICATE_JOURNEY_KEYS:
        return None, 'Represented by another durable collection or excluded technical hold'
    if key.startswith('deactivation_request_') or key.startswith('deactivation_decision_'):
        return None, 'Deactivation outcomes are represented by input receipts'
    raise AlarmHistoryProjectionError(f'Unclassified Journey event: {key}')


# Una cascada debe conservar alarma y ocurrencia de origen y exactamente un efecto.
def _validate_causal_cascade(entry: dict[str, Any]) -> None:
    _nonempty(entry.get('cascade_source_alarm_key'), 'cascade_source_alarm_key')
    _nonempty(entry.get('cascade_source_occurrence_id'), 'cascade_source_occurrence_id')
    effects = sum(
        entry.get(name) is not None
        for name in ('cascade_management_effect_id', 'cascade_deactivation_effect_id')
    )
    if effects != 1:
        raise AlarmHistoryProjectionError('Cascade event requires exactly one causal effect')
    for name in ('cascade_management_effect_id', 'cascade_deactivation_effect_id'):
        if entry.get(name) is not None:
            _nonempty(entry[name], name)



# No aceptar eventos atribuidos a una Rule o Tool si faltan sus claves básicas.
def _validate_history_identity(collection: str, entry: dict[str, Any]) -> None:
    required = {
        'occurrence_changes': ('alarm_key', 'occurrence_id'),
        'episode_changes': ('episode_id',),
        'management_effects': ('alarm_key', 'record_id'),
        'evidence_records': ('alarm_key', 'occurrence_id', 'evidence_id'),
        'deactivation_requests': ('alarm_key', 'request_id', 'source_occurrence_id'),
        'deactivation_effects': ('alarm_key', 'record_id'),
        'assignment_changes': ('alarm_key', 'occurrence_id', 'tool_key', 'change_id'),
        'journey_events': ('alarm_key', 'event_id'),
        'input_receipts': ('input_id', 'input_kind', 'outcome'),
    }[collection]
    for name in required:
        _nonempty(entry.get(name), f'{collection}.{name}')


# El día de materialización se deriva del hecho y no del momento de ejecución.
def _timestamp_field(collection: str, entry: dict[str, Any]) -> str:
    if collection == 'input_receipts':
        return 'event_at' if entry.get('event_at') is not None else 'applied_at'
    if collection in {'occurrence_changes', 'episode_changes'}:
        kind = entry.get('kind')
        if kind == 'STARTED':
            return 'started_at'
        if kind == 'CLOSED':
            return 'ended_at'
        raise AlarmHistoryProjectionError('Unknown lifecycle change kind')
    return _TIMESTAMPS[collection]


# Respeta los valores de evento que publica el Engine sin renombrar ASSIGNED.
def _event_kind(collection: str, entry: dict[str, Any]) -> str:
    field = 'event_key' if collection == 'journey_events' else (
        'input_kind' if collection == 'input_receipts' else 'kind'
    )
    if collection == 'evidence_records':
        field = 'status'
    if collection == 'deactivation_requests':
        return 'REQUEST'
    value = entry.get(field)
    return _nonempty(value, f'{collection}.{field}')


# Fechas estrictamente UTC; no reinterpretar timestamps locales.
def _utc_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise AlarmHistoryProjectionError('History event timestamp must be UTC Z text')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AlarmHistoryProjectionError('Invalid history event timestamp') from error
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise AlarmHistoryProjectionError('History timestamp must be UTC')
    return result


# Las referencias históricas obligatorias no pueden ser vacías.
def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlarmHistoryProjectionError(f'{field} must be non-empty text')
    return value


# Los registros de versiones anteriores pueden no incluir metadatos enriquecidos.
def _optional_string(entry: dict[str, Any], field: str) -> str | None:
    value = entry.get(field)
    if value is None:
        return None
    return _nonempty(value, field)
