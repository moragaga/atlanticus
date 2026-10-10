from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime

import pyarrow as pa

from ada.alarms.history.contract import AlarmHistoryContractError
from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact

_EPISODE_SCHEMA = pa.schema(
    (
        pa.field('episode_id', pa.string(), nullable=False),
        pa.field('priority_group', pa.string(), nullable=False),
        pa.field('started_at_utc', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('ended_at_utc', pa.timestamp('us', tz='UTC'), nullable=True),
        pa.field('closure_reason', pa.string(), nullable=True),
        pa.field('last_event_at_utc', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('last_event_phase', pa.int8(), nullable=False),
        pa.field('historian_fact_id', pa.string(), nullable=False),
        pa.field('source_stream_id', pa.string(), nullable=False),
    )
)


def episodes_schema() -> pa.Schema:
    return _EPISODE_SCHEMA


def episode_started_at(fact: ProjectedAlarmHistoryFact) -> datetime:
    return _episode_row(fact)['started_at_utc']


# Este dataset tiene una sola fila por episodio; OPEN puede evolucionar a CLOSED.
def episodes_table(
    facts: Iterable[ProjectedAlarmHistoryFact], *, current: pa.Table | None = None
) -> pa.Table:
    if isinstance(facts, ProjectedAlarmHistoryFact | str | bytes):
        raise TypeError('facts must be an iterable of episode facts')
    if current is not None and current.schema != _EPISODE_SCHEMA:
        raise AlarmHistoryContractError('Existing episodes publication has an incompatible schema')
    state: dict[str, dict] = {}
    existing = {} if current is None else {row['episode_id']: row for row in current.to_pylist()}
    if current is not None and len(existing) != current.num_rows:
        raise AlarmHistoryContractError('Existing episodes publication contains duplicate ids')
    for fact in facts:
        incoming = _episode_row(fact)
        key = incoming['episode_id']
        previous = state.get(key, existing.get(key))
        state[key] = _advance(previous, incoming)
    return pa.Table.from_pylist(
        [state[key] for key in sorted(state)], schema=_EPISODE_SCHEMA
    )


def _episode_row(fact: ProjectedAlarmHistoryFact) -> dict:
    if not isinstance(fact, ProjectedAlarmHistoryFact) or fact.domain is not AlarmHistoryDomain.EPISODES:
        raise AlarmHistoryContractError('Expected an episodes history fact')
    if fact.source_collection != 'episode_changes' or not fact.episode_id:
        raise AlarmHistoryContractError('Episode history requires a committed episode change')
    try:
        document = json.loads(fact.payload_json)
    except (TypeError, ValueError) as error:
        raise AlarmHistoryContractError('Invalid episode change payload') from error
    if not isinstance(document, dict):
        raise AlarmHistoryContractError('Episode change payload must be an object')
    if (
        document.get('episode_id') != fact.episode_id
        or document.get('priority_group') != fact.priority_group
        or document.get('kind') != fact.event_kind
    ):
        raise AlarmHistoryContractError('Episode change identity mismatch')
    started = _timestamp(document.get('started_at'), 'started_at')
    if fact.event_kind == 'STARTED':
        if document.get('ended_at') is not None or document.get('closure_reason') is not None:
            raise AlarmHistoryContractError('STARTED episode cannot have closure details')
        ended = None
        reason = None
        phase = 0
    elif fact.event_kind == 'CLOSED':
        ended = _timestamp(document.get('ended_at'), 'ended_at')
        reason = document.get('closure_reason')
        if not isinstance(reason, str) or not reason.strip():
            raise AlarmHistoryContractError('CLOSED episode requires closure_reason')
        if ended < started:
            raise AlarmHistoryContractError('Episode ended before it started')
        phase = 1
    else:
        raise AlarmHistoryContractError('Unknown episode change kind')
    if (
        fact.event_at_utc != (ended if ended is not None else started)
        or fact.day_utc != fact.event_at_utc.date()
    ):
        raise AlarmHistoryContractError('Episode event timestamp mismatch')
    return {
        'episode_id': fact.episode_id,
        'priority_group': fact.priority_group,
        'started_at_utc': started,
        'ended_at_utc': ended,
        'closure_reason': reason,
        'last_event_at_utc': fact.event_at_utc,
        'last_event_phase': phase,
        'historian_fact_id': fact.historian_fact_id,
        'source_stream_id': fact.source_stream_id,
    }


def _advance(previous: dict | None, incoming: dict) -> dict:
    if previous is None:
        return incoming
    for key in ('episode_id', 'priority_group', 'started_at_utc', 'source_stream_id'):
        if previous[key] != incoming[key]:
            raise AlarmHistoryContractError('Conflicting episode identity or origin')
    if previous['last_event_phase'] == 1:
        if incoming['last_event_phase'] == 1 and (
            previous['ended_at_utc'] != incoming['ended_at_utc']
            or previous['closure_reason'] != incoming['closure_reason']
        ):
            raise AlarmHistoryContractError('Conflicting closed episode facts')
        return previous
    if incoming['last_event_phase'] == 0:
        return previous
    return incoming


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise AlarmHistoryContractError(f'Episode {field} must be UTC Z text')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AlarmHistoryContractError(f'Episode {field} is invalid') from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise AlarmHistoryContractError(f'Episode {field} must be UTC')
    return parsed
