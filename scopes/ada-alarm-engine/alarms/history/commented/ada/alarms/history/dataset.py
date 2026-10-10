from __future__ import annotations

from collections.abc import Iterable

import pyarrow as pa

from ada.alarms.history.contract import AlarmHistoryContractError
from ada.contracts.alarms.history_projection import ProjectedAlarmHistoryFact

_HISTORY_SCHEMA = pa.schema(
    (
        pa.field('historian_fact_id', pa.string(), nullable=False),
        pa.field('event_at_utc', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('event_kind', pa.string(), nullable=False),
        pa.field('alarm_key', pa.string(), nullable=True),
        pa.field('occurrence_id', pa.string(), nullable=True),
        pa.field('episode_id', pa.string(), nullable=True),
        pa.field('priority_group', pa.string(), nullable=False),
        pa.field('source_stream_id', pa.string(), nullable=False),
        pa.field('source_commit_id', pa.string(), nullable=False),
        pa.field('source_journal_segment_id', pa.string(), nullable=False),
        pa.field('source_journal_byte_offset', pa.int64(), nullable=False),
        pa.field('source_collection', pa.string(), nullable=False),
        pa.field('source_ordinal', pa.int64(), nullable=False),
        pa.field('source_facts_sha256', pa.string(), nullable=False),
        pa.field('timestamp_provenance', pa.string(), nullable=False),
        pa.field('payload_json', pa.string(), nullable=False),
    )
)


# Los seis destinos comparten un esquema estable con provenance del registro original.
def history_schema() -> pa.Schema:
    return _HISTORY_SCHEMA


# Materializa columnas tipadas sin reinterpretar el JSON de los hechos de origen.
def history_table(facts: Iterable[ProjectedAlarmHistoryFact]) -> pa.Table:
    if isinstance(facts, ProjectedAlarmHistoryFact | str | bytes):
        raise TypeError('facts must be an iterable of projected history facts')
    try:
        items = tuple(facts)
    except TypeError as error:
        raise TypeError('facts must be an iterable of projected history facts') from error
    if not all(isinstance(item, ProjectedAlarmHistoryFact) for item in items):
        raise TypeError('facts must contain ProjectedAlarmHistoryFact values')
    rows = [
        {
            'historian_fact_id': item.historian_fact_id,
            'event_at_utc': item.event_at_utc,
            'event_kind': item.event_kind,
            'alarm_key': item.alarm_key,
            'occurrence_id': item.occurrence_id,
            'episode_id': item.episode_id,
            'priority_group': item.priority_group,
            'source_stream_id': item.source_stream_id,
            'source_commit_id': item.source_commit_id,
            'source_journal_segment_id': item.source_journal_segment_id,
            'source_journal_byte_offset': item.source_journal_byte_offset,
            'source_collection': item.source_collection,
            'source_ordinal': item.source_ordinal,
            'source_facts_sha256': item.source_facts_sha256,
            'timestamp_provenance': item.timestamp_provenance,
            'payload_json': item.payload_json,
        }
        for item in items
    ]
    try:
        return pa.Table.from_pylist(rows, schema=_HISTORY_SCHEMA)
    except (pa.ArrowException, TypeError, ValueError, OverflowError) as error:
        raise AlarmHistoryContractError('History rows do not match Parquet schema') from error
