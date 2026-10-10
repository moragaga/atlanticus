from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ada.alarms.history import (
    AlarmHistoryContractError,
    AlarmHistoryMaterializer,
    episodes_schema,
    history_destination,
)
from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


def episode_fact(kind: str, *, number: int, end='2026-10-11T02:00:00Z',
                 start='2026-10-10T23:30:00Z', group='chancador-group-priority',
                 episode='episode-001') -> ProjectedAlarmHistoryFact:
    document = {
        'kind': kind, 'episode_id': episode, 'priority_group': group,
        'started_at': start, 'ended_at': end if kind == 'CLOSED' else None,
        'closure_reason': 'condition_normalized' if kind == 'CLOSED' else None,
    }
    at = datetime.fromisoformat((end if kind == 'CLOSED' else start).replace('Z', '+00:00'))
    return ProjectedAlarmHistoryFact(
        domain=AlarmHistoryDomain.EPISODES,
        historian_fact_id=f'{number:064x}',
        event_kind=kind, event_at_utc=at, day_utc=at.date(),
        alarm_key=None, occurrence_id=None, episode_id=episode,
        priority_group=group, source_stream_id='runtime-A',
        source_commit_id=f'C-{number}', source_journal_segment_id='segment-A',
        source_journal_byte_offset=number, source_collection='episode_changes',
        source_ordinal=0, source_facts_sha256='a' * 64,
        timestamp_provenance='SOURCE_EVENT_AT',
        payload_json=json.dumps(document, sort_keys=True),
    )


def _runtime(tmp_path):
    return DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))


def _rows(runtime, fact):
    definition, target = history_destination(fact)
    return runtime.read_table(definition=definition, target=target).table.to_pylist()


def test_open_close_one_episode_on_start_day_across_midnight(tmp_path):
    runtime = _runtime(tmp_path)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    start = episode_fact('STARTED', number=1)
    end = episode_fact('CLOSED', number=2)
    definition, target = history_destination(start)
    assert history_destination(end) == (definition, target)
    assert definition.resolve_route_segments(target) == (
        'history', 'episodes', 'year=2026', 'month=10', 'day=10',
    )
    first = materializer.materialize(facts=[start])
    assert first.targets_committed == 1
    assert _rows(runtime, start)[0]['ended_at_utc'] is None
    second = materializer.materialize(facts=[end])
    assert second.targets_committed == 1
    rows = _rows(runtime, start)
    assert len(rows) == 1
    assert rows[0]['started_at_utc'] == datetime(2026, 10, 10, 23, 30, tzinfo=UTC)
    assert rows[0]['ended_at_utc'] == datetime(2026, 10, 11, 2, tzinfo=UTC)
    assert rows[0]['closure_reason'] == 'condition_normalized'
    assert rows[0]['historian_fact_id'] == end.historian_fact_id
    assert runtime.read_table(definition=definition, target=target).table.schema == episodes_schema()
    assert materializer.materialize(facts=[end]).targets_unchanged == 1
    assert materializer.materialize(facts=[start]).targets_unchanged == 1
    assert _rows(runtime, start) == rows


def test_closed_before_started_is_still_final(tmp_path):
    runtime = _runtime(tmp_path)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    start = episode_fact('STARTED', number=1)
    end = episode_fact('CLOSED', number=2)
    assert materializer.materialize(facts=[end]).targets_committed == 1
    assert materializer.materialize(facts=[start]).targets_unchanged == 1
    assert len(_rows(runtime, start)) == 1
    assert _rows(runtime, start)[0]['last_event_phase'] == 1


def test_same_batch_start_close_and_other_episodes(tmp_path):
    runtime = _runtime(tmp_path)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    start = episode_fact('STARTED', number=1)
    end = episode_fact('CLOSED', number=2)
    second = episode_fact('STARTED', number=3, episode='episode-002')
    result = materializer.materialize(facts=[end, second, start, start])
    assert result.facts_received == 4
    assert result.facts_unique == 3
    assert result.targets_committed == 1
    rows = _rows(runtime, start)
    assert len(rows) == 2
    assert {row['episode_id']: row['last_event_phase'] for row in rows} == {
        'episode-001': 1, 'episode-002': 0,
    }
    assert materializer.materialize(facts=[start, end, second]).targets_unchanged == 1


def test_conflicting_episode_closure_does_not_overwrite(tmp_path):
    runtime = _runtime(tmp_path)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    end = episode_fact('CLOSED', number=2)
    materializer.materialize(facts=[end])
    conflict = episode_fact('CLOSED', number=3, end='2026-10-11T03:00:00Z')
    with pytest.raises(AlarmHistoryContractError, match='Conflicting closed'):
        materializer.materialize(facts=[conflict])
    assert _rows(runtime, end)[0]['ended_at_utc'] == end.event_at_utc


def test_conflicting_identity_or_bad_timestamp_rejected(tmp_path):
    runtime = _runtime(tmp_path)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    start = episode_fact('STARTED', number=1)
    materializer.materialize(facts=[start])
    conflict = episode_fact('CLOSED', number=2, group='other-group')
    with pytest.raises(AlarmHistoryContractError, match='Conflicting episode identity'):
        materializer.materialize(facts=[conflict])
    invalid = replace(start, payload_json='{"kind":"STARTED"}')
    with pytest.raises(AlarmHistoryContractError):
        materializer.materialize(facts=[invalid])


def test_start_and_close_same_instant_remains_closed(tmp_path):
    runtime = _runtime(tmp_path)
    start = episode_fact('STARTED', number=1, start='2026-10-10T12:00:00Z')
    end = episode_fact('CLOSED', number=2, start='2026-10-10T12:00:00Z',
                       end='2026-10-10T12:00:00Z')
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    materializer.materialize(facts=[end, start])
    assert _rows(runtime, start)[0]['last_event_phase'] == 1
    assert materializer.materialize(facts=[start]).targets_unchanged == 1


def test_no_episode_rows_in_lifecycle(tmp_path):
    runtime = _runtime(tmp_path)
    episode = episode_fact('STARTED', number=1)
    result = AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[episode])
    assert result.targets_committed == 1
    assert not list(tmp_path.glob('history/lifecycle/**/*.parquet'))
