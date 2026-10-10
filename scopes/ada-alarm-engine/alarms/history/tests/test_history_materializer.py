from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ada.alarms.history import (
    AlarmHistoryContractError,
    AlarmHistoryMaterializationError,
    AlarmHistoryMaterializer,
    history_destination,
)
from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


@pytest.fixture
def facts():
    now = datetime(2026, 10, 10, 23, 59, tzinfo=UTC)

    def make(number, domain, *, key='molienda/presion_alta', at=now):
        return ProjectedAlarmHistoryFact(
            domain=domain,
            historian_fact_id=f'{number:064x}',
            event_kind='STARTED',
            event_at_utc=at,
            day_utc=at.date(),
            alarm_key=key,
            occurrence_id=f'O-{number}',
            episode_id='episode-1',
            priority_group='molienda',
            source_stream_id='plant-1',
            source_commit_id=f'C-{number}',
            source_journal_segment_id='S-1',
            source_journal_byte_offset=number,
            source_collection='journey_events',
            source_ordinal=number,
            source_facts_sha256='b' * 64,
            timestamp_provenance='SOURCE_EVENT_AT',
            payload_json='{"sample":true}',
        )

    return make


@pytest.fixture
def runtime(tmp_path):
    return DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))


def _read_rows(runtime, fact):
    definition, target = history_destination(fact)
    return runtime.read_table(definition=definition, target=target).table.to_pylist()


def test_non_episode_histories_and_daily_partition_isolation(runtime, facts):
    domains = tuple(domain for domain in AlarmHistoryDomain if domain is not AlarmHistoryDomain.EPISODES)
    rows = [facts(i, domain) for i, domain in enumerate(domains, start=1)]
    rows.extend([
        facts(7, AlarmHistoryDomain.EVIDENCE, key='molienda/temperatura_alta'),
        facts(8, AlarmHistoryDomain.EVIDENCE, at=datetime(2026, 10, 11, 0, 1, tzinfo=UTC)),
    ])
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    result = materializer.materialize(facts=rows)
    assert result.facts_unique == 8
    assert result.targets_processed == 8
    assert result.targets_committed == 8
    for fact in rows:
        actual = _read_rows(runtime, fact)
        assert len(actual) == 1
        assert actual[0]['historian_fact_id'] == fact.historian_fact_id
        assert actual[0]['payload_json'] == fact.payload_json


def test_replay_is_idempotent_even_with_duplicate_input(runtime, facts):
    first = facts(1, AlarmHistoryDomain.VISIBILITY)
    second = facts(2, AlarmHistoryDomain.VISIBILITY)
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    initial = materializer.materialize(facts=[first, second, first])
    assert (initial.facts_received, initial.facts_unique, initial.targets_committed) == (3, 2, 1)
    replay = materializer.materialize(facts=[second, first])
    assert replay.targets_unchanged == 1
    stored = _read_rows(runtime, first)
    assert len(stored) == 2
    assert {row['historian_fact_id'] for row in stored} == {
        first.historian_fact_id, second.historian_fact_id
    }


def test_bad_identity_is_rejected_before_writing_any_partition(runtime, facts, tmp_path):
    good = facts(1, AlarmHistoryDomain.LIFECYCLE)
    invalid = facts(2, AlarmHistoryDomain.EVIDENCE, key='family/rule/ambiguous')
    with pytest.raises(AlarmHistoryContractError):
        AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[good, invalid])
    assert not list(tmp_path.rglob('*.parquet'))


def test_conflicting_fact_id_rejected_before_any_publication(runtime, facts, tmp_path):
    original = facts(1, AlarmHistoryDomain.CASCADE)
    conflict = replace(original, payload_json='{"altered":true}')
    with pytest.raises(AlarmHistoryMaterializationError, match='conflicting'):
        AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[original, conflict])
    assert not list(tmp_path.rglob('*.parquet'))


def test_partial_failure_can_be_replayed_without_duplicates(runtime, facts):
    first = facts(1, AlarmHistoryDomain.CASCADE)
    second = facts(2, AlarmHistoryDomain.MANAGEMENT)
    destinations = sorted((history_destination(first)[1].identifier, history_destination(second)[1].identifier))

    class FaultOnce:
        def __init__(self):
            self.attempts = 0

        def merge(self, **kwargs):
            self.attempts += 1
            if self.attempts == 2:
                raise OSError('simulated publication failure')
            return runtime.merge(**kwargs)

    with pytest.raises(OSError, match='simulated'):
        AlarmHistoryMaterializer(runtime=FaultOnce()).materialize(facts=[first, second])
    recovery = AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[first, second])
    assert recovery.target_identifiers == tuple(destinations)
    assert recovery.targets_committed == 1
    assert recovery.targets_unchanged == 1
    assert len(_read_rows(runtime, first)) == 1
    assert len(_read_rows(runtime, second)) == 1


def test_fencing_callback_is_checked_before_each_publication(runtime, facts):
    current = [0]

    def check():
        current[0] += 1
        if current[0] >= 5:
            raise RuntimeError('lease lost')

    first = facts(1, AlarmHistoryDomain.CASCADE)
    second = facts(2, AlarmHistoryDomain.MANAGEMENT)
    with pytest.raises(RuntimeError, match='lease lost'):
        AlarmHistoryMaterializer(runtime=runtime).materialize(
            facts=[first, second], check_current=check
        )
    replay = AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[first, second])
    assert replay.targets_processed == 2


def test_empty_input_does_not_publish(runtime):
    result = AlarmHistoryMaterializer(runtime=runtime).materialize(facts=[])
    assert result.facts_unique == 0
    assert result.targets_processed == 0
