from __future__ import annotations

from dataclasses import dataclass

import pytest

import ada.processes.alarm_historian.reader as reader_module
from ada.contracts.alarms.facts_stream import FactsStreamPosition
from ada.contracts.alarms.history_projection import AlarmHistoryProjection, ExcludedAlarmHistoryFact
from ada.processes.alarm_historian import AlarmHistorianReader


@dataclass(frozen=True)
class Commit:
    position: FactsStreamPosition


@pytest.fixture
def positions():
    return tuple(
        FactsStreamPosition(
            segment_path='facts/year=2026/month=10/day=10/hour=12/part-0000.jsonl',
            record_start=i * 100,
            record_end=(i + 1) * 100,
            record_sha256=f'{i + 1:064x}',
            artifact_ref={'source_key': 'alarms'},
        )
        for i in range(4)
    )


def test_reads_bounded_committed_records_and_retains_last_full_position(
    tmp_path, monkeypatch, positions
):
    consumed = []

    def source(*, root, after):
        assert root == tmp_path
        assert after is None
        for position in positions:
            consumed.append(position)
            yield Commit(position)

    def project(*, facts, stream_id):
        assert stream_id == 'plant-1'
        return AlarmHistoryProjection((), (ExcludedAlarmHistoryFact('journey_events', 0, 'skipped'),))

    monkeypatch.setattr(reader_module, 'iter_committed_facts', source)
    monkeypatch.setattr(reader_module, 'project_committed_alarm_facts', project)
    batch = AlarmHistorianReader(facts_root=tmp_path, stream_id='plant-1', max_records=2).read(
        after=None
    )
    assert batch.records_read == 2
    assert batch.excluded_count == 2
    assert batch.facts == ()
    assert batch.last_position == positions[1]
    assert consumed == list(positions[:2])


def test_no_new_records_keeps_position_and_does_not_invent_work(tmp_path, monkeypatch, positions):
    def source(*, root, after):
        assert after == positions[0]
        return iter(())

    monkeypatch.setattr(reader_module, 'iter_committed_facts', source)
    batch = AlarmHistorianReader(facts_root=tmp_path, stream_id='plant-1', max_records=2).read(
        after=positions[0]
    )
    assert batch.records_read == 0
    assert batch.last_position == positions[0]
    assert batch.facts == ()
    assert batch.excluded_count == 0


def test_projection_failure_does_not_report_success(tmp_path, monkeypatch, positions):
    monkeypatch.setattr(
        reader_module, 'iter_committed_facts', lambda **kwargs: iter([Commit(positions[0])])
    )

    def fail(*, facts, stream_id):
        raise ValueError('Unknown Journey event')

    monkeypatch.setattr(reader_module, 'project_committed_alarm_facts', fail)
    with pytest.raises(ValueError, match='Unknown Journey event'):
        AlarmHistorianReader(facts_root=tmp_path, stream_id='plant-1', max_records=1).read(
            after=None
        )


@pytest.mark.parametrize('limit', [0, -1, True, 1.5, '4'])
def test_invalid_max_records_rejected(tmp_path, limit):
    with pytest.raises(ValueError):
        AlarmHistorianReader(facts_root=tmp_path, stream_id='plant-1', max_records=limit)
