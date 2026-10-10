from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from ada.contracts.alarms.facts_stream import FactsStreamPosition
from ada.processes.alarm_historian import (
    AlarmHistorianCheckpointError,
    AlarmHistorianCheckpointStore,
)
from atlanticus.state import AtomicJsonStore


@pytest.fixture
def position():
    return FactsStreamPosition(
        segment_path='facts/year=2026/month=10/day=10/hour=12/part-0000.jsonl',
        record_start=0,
        record_end=213,
        record_sha256='a' * 64,
        artifact_ref={'source_key': 'alarm-configuration', 'resolution_key': {'revision': 3}},
    )


def _store(tmp_path, *, stream_id='plant-1', application='ada-command-center'):
    return AlarmHistorianCheckpointStore(
        root=tmp_path, stream_id=stream_id, producer_application=application
    )


def test_initial_checkpoint_is_missing_and_roundtrip_preserves_full_position(tmp_path, position):
    store = _store(tmp_path)
    assert store.read() is None
    saved = store.save(position)
    assert saved.position == position
    assert _store(tmp_path).read() == saved


def test_same_position_is_idempotent_and_rewind_is_rejected(tmp_path, position):
    store = _store(tmp_path)
    first = store.save(position)
    assert store.save(position) == first
    with pytest.raises(AlarmHistorianCheckpointError, match='backwards'):
        store.save(replace(position, record_end=212))
    assert store.read() == first


def test_same_offset_cannot_change_digest_or_artifact(tmp_path, position):
    store = _store(tmp_path)
    store.save(position)
    with pytest.raises(AlarmHistorianCheckpointError, match='position has changed'):
        store.save(replace(position, record_sha256='b' * 64))
    with pytest.raises(AlarmHistorianCheckpointError, match='position has changed'):
        store.save(replace(position, artifact_ref={'different': True}))


def test_source_identity_cannot_change(tmp_path, position):
    _store(tmp_path).save(position)
    with pytest.raises(AlarmHistorianCheckpointError, match='source identity'):
        _store(tmp_path, stream_id='plant-2').read()
    with pytest.raises(AlarmHistorianCheckpointError, match='source identity'):
        _store(tmp_path, application='other-application').read()


def test_modified_document_without_valid_digest_is_rejected(tmp_path, position):
    store = _store(tmp_path)
    store.save(position)
    atomic = AtomicJsonStore(root_path=tmp_path)
    doc = atomic.read('state/historian-checkpoint.json')
    doc['position']['record_end'] += 1
    atomic.replace('state/historian-checkpoint.json', doc)
    with pytest.raises(AlarmHistorianCheckpointError, match='integrity'):
        store.read()


def test_modified_document_with_valid_digest_but_invalid_position_is_rejected(tmp_path, position):
    store = _store(tmp_path)
    store.save(position)
    atomic = AtomicJsonStore(root_path=tmp_path)
    doc = atomic.read('state/historian-checkpoint.json')
    doc['position']['record_start'] = -1
    raw = {key: value for key, value in doc.items() if key != 'sha256'}
    doc['sha256'] = hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        .encode('utf-8')
    ).hexdigest()
    atomic.replace('state/historian-checkpoint.json', doc)
    with pytest.raises(AlarmHistorianCheckpointError, match='offsets'):
        store.read()


def test_invalid_position_cannot_be_persisted(tmp_path, position):
    store = _store(tmp_path)
    with pytest.raises(AlarmHistorianCheckpointError, match='segment'):
        store.save(replace(position, segment_path='../outside'))
    assert store.read() is None


def test_forward_progress_keeps_new_full_position(tmp_path, position):
    store = _store(tmp_path)
    store.save(position)
    next_position = replace(position, record_start=213, record_end=425, record_sha256='b' * 64)
    assert store.save(next_position).position == next_position
    assert store.read().position == next_position
