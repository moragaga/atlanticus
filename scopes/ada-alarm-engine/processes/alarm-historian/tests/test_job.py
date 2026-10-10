from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from ada.alarms.history import history_destination
from ada.contracts.alarms.facts_stream import FactsStreamPosition
from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact
from ada.processes.alarm_historian import (
    AlarmHistorianBatch,
    AlarmHistorianCheckpointStore,
    AlarmHistorianJob,
    AlarmHistorianReader,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


class _Reader(AlarmHistorianReader):
    def __init__(self, *, facts_root, batch):
        super().__init__(facts_root=facts_root, stream_id='plant-1', max_records=2)
        self.batch = batch
        self.read_after = []

    def read(self, *, after):
        self.read_after.append(after)
        return self.batch


class _Context:
    def __init__(self, *, fail_fence_at=None):
        self.fail_fence_at = fail_fence_at
        self.fences = 0
        self.depth = 0
        self.assertions = 0
        self.work_count = 0
        self.facts = {}
        self.cancelled = False

    def raise_if_cancelled(self):
        if self.cancelled:
            raise RuntimeError('Execution cancelled')

    def assert_lease_current(self):
        assert self.depth == 0, 'nested lease authority verification'
        self.assertions += 1

    @contextmanager
    def fenced_mutation(self):
        assert self.depth == 0, 'nested mutation fence'
        self.fences += 1
        if self.fences == self.fail_fence_at:
            raise RuntimeError('Lease ownership was lost')
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def mark_iteration_work(self):
        self.work_count += 1

    def set_iteration_fact(self, key, value):
        self.facts[key] = value


class _MergeOnceFailure:
    def __init__(self, runtime, *, failure_at):
        self.runtime = runtime
        self.failure_at = failure_at
        self.attempts = 0

    def merge(self, **kwargs):
        self.attempts += 1
        if self.attempts == self.failure_at:
            raise OSError('Simulated Parquet publication failure')
        return self.runtime.merge(**kwargs)


def _position(number):
    return FactsStreamPosition(
        segment_path='facts/year=2026/month=10/day=10/hour=12/part-0000.jsonl',
        record_start=(number - 1) * 120,
        record_end=number * 120,
        record_sha256=f'{number:064x}',
        artifact_ref={'source_key': 'alarms'},
    )


def _fact(number, domain):
    when = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    return ProjectedAlarmHistoryFact(
        domain=domain,
        historian_fact_id=f'{number:064x}',
        event_kind='STARTED',
        event_at_utc=when,
        day_utc=when.date(),
        alarm_key='plant/high_pressure',
        occurrence_id='occ-1',
        episode_id='episode-1',
        priority_group='plant',
        source_stream_id='plant-1',
        source_commit_id=f'commit-{number}',
        source_journal_segment_id='segment-1',
        source_journal_byte_offset=number,
        source_collection='journey_events',
        source_ordinal=number,
        source_facts_sha256='f' * 64,
        timestamp_provenance='SOURCE_EVENT_AT',
        payload_json='{"status":"STARTED"}',
    )


def _setup(tmp_path, batch):
    checkpoint = AlarmHistorianCheckpointStore(
        root=tmp_path / 'checkpoint',
        stream_id='plant-1',
        producer_application='ada-command-center',
    )
    reader = _Reader(facts_root=tmp_path, batch=batch)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'parquet'))
    return reader, checkpoint, runtime


def _run(reader, checkpoint, runtime, context=None):
    context = _Context() if context is None else context
    result = AlarmHistorianJob(reader=reader, checkpoint=checkpoint, runtime=runtime).run_iteration(
        context
    )
    return result, context


def _rows(runtime, fact):
    definition, target = history_destination(fact)
    return runtime.read_table(definition=definition, target=target).table.to_pylist()


def test_empty_iteration_does_not_publish_or_advance_checkpoint(tmp_path):
    reader, checkpoint, runtime = _setup(tmp_path, AlarmHistorianBatch((), 0, 0, None))
    result, context = _run(reader, checkpoint, runtime)
    assert result.records_read == 0
    assert not result.checkpoint_advanced
    assert context.work_count == 0
    assert context.fences == 0
    assert checkpoint.read() is None
    assert reader.read_after == [None]


def test_all_excluded_records_advance_without_parquet_writes(tmp_path):
    position = _position(2)
    reader, checkpoint, runtime = _setup(tmp_path, AlarmHistorianBatch((), 4, 2, position))
    result, context = _run(reader, checkpoint, runtime)
    assert (result.records_read, result.facts_excluded, result.facts_projected) == (2, 4, 0)
    assert result.checkpoint_advanced
    assert context.fences == 1
    assert context.work_count == 1
    assert checkpoint.read().position == position
    assert not list((tmp_path / 'parquet').rglob('*.parquet'))


def test_multiple_destinations_confirm_before_checkpoint_and_use_separate_fences(tmp_path):
    first = _fact(1, AlarmHistoryDomain.LIFECYCLE)
    second = _fact(2, AlarmHistoryDomain.MANAGEMENT)
    position = _position(2)
    reader, checkpoint, runtime = _setup(
        tmp_path, AlarmHistorianBatch((first, second), 1, 2, position)
    )
    result, context = _run(reader, checkpoint, runtime)
    assert (result.targets_committed, result.targets_unchanged) == (2, 0)
    assert (result.facts_projected, result.facts_excluded) == (2, 1)
    assert context.fences == 3
    assert context.assertions >= 3
    assert context.work_count == 1
    assert checkpoint.read().position == position
    assert len(_rows(runtime, first)) == 1
    assert len(_rows(runtime, second)) == 1
    assert context.facts['checkpoint_advanced'] is True


def test_partial_parquet_failure_does_not_advance_checkpoint_and_replay_is_idempotent(tmp_path):
    first = _fact(1, AlarmHistoryDomain.LIFECYCLE)
    second = _fact(2, AlarmHistoryDomain.MANAGEMENT)
    position = _position(2)
    reader, checkpoint, runtime = _setup(
        tmp_path, AlarmHistorianBatch((first, second), 0, 2, position)
    )
    broken = _MergeOnceFailure(runtime, failure_at=2)
    context = _Context()
    with pytest.raises(OSError, match='Simulated Parquet'):
        _run(reader, checkpoint, broken, context)
    assert checkpoint.read() is None
    assert context.work_count == 0
    assert len(_rows(runtime, first)) == 1

    result, recovered = _run(reader, checkpoint, runtime)
    assert result.targets_unchanged == 1
    assert result.targets_committed == 1
    assert checkpoint.read().position == position
    assert recovered.work_count == 1
    assert len(_rows(runtime, first)) == 1
    assert len(_rows(runtime, second)) == 1
    assert reader.read_after == [None, None]


def test_lost_lease_between_destinations_blocks_later_writes_and_checkpoint(tmp_path):
    first = _fact(1, AlarmHistoryDomain.LIFECYCLE)
    second = _fact(2, AlarmHistoryDomain.MANAGEMENT)
    reader, checkpoint, runtime = _setup(
        tmp_path, AlarmHistorianBatch((first, second), 0, 2, _position(2))
    )
    context = _Context(fail_fence_at=2)
    with pytest.raises(RuntimeError, match='Lease ownership'):
        _run(reader, checkpoint, runtime, context)
    assert checkpoint.read() is None
    assert context.work_count == 0
    assert len(_rows(runtime, first)) == 1
    assert not list((tmp_path / 'checkpoint').rglob('*.json'))

    result, _ = _run(reader, checkpoint, runtime)
    assert (result.targets_unchanged, result.targets_committed) == (1, 1)
    assert checkpoint.read().position == _position(2)


def test_checkpoint_write_failure_leaves_destinations_replayable(tmp_path, monkeypatch):
    first = _fact(1, AlarmHistoryDomain.CASCADE)
    reader, checkpoint, runtime = _setup(
        tmp_path, AlarmHistorianBatch((first,), 0, 1, _position(1))
    )
    original_save = checkpoint.save
    fail = [True]

    def fail_once(position):
        if fail[0]:
            fail[0] = False
            raise OSError('Simulated checkpoint failure')
        return original_save(position)

    monkeypatch.setattr(checkpoint, 'save', fail_once)
    context = _Context()
    with pytest.raises(OSError, match='Simulated checkpoint'):
        _run(reader, checkpoint, runtime, context)
    assert checkpoint.read() is None
    assert context.work_count == 0
    assert len(_rows(runtime, first)) == 1

    result, _ = _run(reader, checkpoint, runtime)
    assert result.targets_unchanged == 1
    assert checkpoint.read().position == _position(1)
    assert len(_rows(runtime, first)) == 1


def test_lost_lease_before_checkpoint_replays_successful_publications(tmp_path):
    fact = _fact(1, AlarmHistoryDomain.VISIBILITY)
    reader, checkpoint, runtime = _setup(tmp_path, AlarmHistorianBatch((fact,), 0, 1, _position(1)))
    with pytest.raises(RuntimeError, match='Lease ownership'):
        _run(reader, checkpoint, runtime, _Context(fail_fence_at=2))
    assert checkpoint.read() is None
    assert len(_rows(runtime, fact)) == 1
    result, _ = _run(reader, checkpoint, runtime)
    assert result.targets_unchanged == 1
    assert checkpoint.read().position == _position(1)


def test_existing_checkpoint_is_used_to_resume_exact_facts_position(tmp_path):
    checkpoint_position = _position(1)
    later_position = _position(2)
    reader, checkpoint, runtime = _setup(
        tmp_path, AlarmHistorianBatch((), 1, 1, later_position)
    )
    checkpoint.save(checkpoint_position)
    _run(reader, checkpoint, runtime)
    assert reader.read_after == [checkpoint_position]
    assert checkpoint.read().position == later_position


def test_invalid_nonempty_batch_cannot_advance_checkpoint(tmp_path):
    reader, checkpoint, runtime = _setup(tmp_path, AlarmHistorianBatch((), 0, 1, None))
    with pytest.raises(ValueError, match='no confirmed final position'):
        _run(reader, checkpoint, runtime)
    assert checkpoint.read() is None
