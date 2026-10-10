from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pytest

from ada.alarms.history import (
    AlarmHistoryContractError,
    AlarmHistoryMaterializer,
    evidence_definition,
    history_definition,
    history_destination,
    history_schema,
    history_table,
)
from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact
from atlanticus.datasets.core import DatasetDefinition
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


@pytest.fixture
def make_fact():
    def create(
        number=1,
        *,
        domain=AlarmHistoryDomain.EVIDENCE,
        alarm_key='molienda/presion_alta',
        event_at=datetime(2026, 10, 10, 23, 59, tzinfo=UTC),
    ):
        return ProjectedAlarmHistoryFact(
            domain=domain,
            historian_fact_id=f'{number:064x}',
            event_kind='ACTIVE',
            event_at_utc=event_at,
            day_utc=event_at.date(),
            alarm_key=alarm_key,
            occurrence_id='occ-1',
            episode_id='episode-1',
            priority_group='grupo',
            source_stream_id='engine-1',
            source_commit_id='C-1',
            source_journal_segment_id='S-1',
            source_journal_byte_offset=number,
            source_collection='evidence_records',
            source_ordinal=0,
            source_facts_sha256='f' * 64,
            timestamp_provenance='SOURCE_EVENT_AT',
            payload_json='{"status":"ACTIVE"}',
        )

    return create


def test_each_non_evidence_domain_has_a_daily_history_target(make_fact):
    for domain in AlarmHistoryDomain:
        if domain in {AlarmHistoryDomain.EVIDENCE, AlarmHistoryDomain.EPISODES}:
            continue
        fact = make_fact(domain=domain, alarm_key=None)
        definition, target = history_destination(fact)
        assert isinstance(definition, DatasetDefinition)
        assert definition is history_definition(domain)
        assert definition.resolve_route_segments(target) == (
            'history', domain.value, 'year=2026', 'month=10', 'day=10'
        )


def test_evidence_partition_uses_separate_family_and_rule(make_fact):
    definition, target = history_destination(make_fact())
    assert definition == evidence_definition('molienda/presion_alta')
    assert definition.resolve_route_segments(target) == (
        'evidence', 'molienda', 'presion_alta',
        'year=2026', 'month=10', 'day=10',
    )


@pytest.mark.parametrize('key', [
    'CHANCADOR/alarm-6823abff9769',
    'molienda/regla-roja',
    'family.name/rule-1_2',
])
def test_evidence_preserves_valid_dataset_identity_segments(make_fact, key):
    definition, target = history_destination(make_fact(alarm_key=key))
    family, rule = key.split('/')
    assert definition.resolve_route_segments(target) == (
        'evidence', family, rule, 'year=2026', 'month=10', 'day=10'
    )


def test_evidence_with_real_hyphenated_identity_publishes_and_replays(make_fact, tmp_path):
    fact = make_fact(alarm_key='CHANCADOR/alarm-6823abff9769')
    definition, target = history_destination(fact)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))
    materializer = AlarmHistoryMaterializer(runtime=runtime)
    initial = materializer.materialize(facts=[fact])
    assert initial.targets_committed == 1
    replay = materializer.materialize(facts=[fact])
    assert replay.targets_unchanged == 1
    rows = runtime.read_table(definition=definition, target=target).table.to_pylist()
    assert len(rows) == 1
    assert rows[0]['alarm_key'] == 'CHANCADOR/alarm-6823abff9769'
    assert rows[0]['historian_fact_id'] == fact.historian_fact_id


def test_midnight_event_moves_to_next_partition(make_fact):
    start = make_fact(event_at=datetime(2026, 10, 10, 23, 59, tzinfo=UTC))
    end = make_fact(2, event_at=start.event_at_utc + timedelta(minutes=1))
    assert history_destination(start)[1] != history_destination(end)[1]


@pytest.mark.parametrize('key', [
    None, '', 'molienda', '/presion', 'molienda/',
    'molienda/presion/alta', 'molienda/../presion',
    'molienda/regla roja', 'molienda/área', 'molienda\\otra',
    'molienda/.', 'molienda/..', '-family/regla',
    'molienda/-regla', '_family/regla',
])
def test_evidence_rejects_unsafe_or_ambiguous_ids(make_fact, key):
    with pytest.raises(AlarmHistoryContractError):
        history_destination(make_fact(alarm_key=key))


def test_timestamp_and_partition_invariants(make_fact):
    fact = make_fact()
    with pytest.raises(AlarmHistoryContractError):
        history_destination(replace(fact, day_utc=fact.day_utc - timedelta(days=1)))
    with pytest.raises(AlarmHistoryContractError):
        history_destination(replace(fact, event_at_utc=fact.event_at_utc.replace(tzinfo=None)))


def test_arrow_schema_and_full_provenance(make_fact):
    rows = history_table((make_fact(), make_fact(2)))
    assert rows.schema == history_schema()
    assert rows.schema.field('event_at_utc').type == pa.timestamp('us', tz='UTC')
    assert rows.schema.field('historian_fact_id').nullable is False
    assert rows.num_rows == 2
    assert rows.to_pylist()[0]['source_stream_id'] == 'engine-1'
    assert rows.to_pylist()[0]['source_facts_sha256'] == 'f' * 64
    assert rows.to_pylist()[0]['payload_json'] == '{"status":"ACTIVE"}'
