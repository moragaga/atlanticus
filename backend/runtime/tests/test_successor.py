from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.runtime.errors import AtlanticusRuntimeError
from atlanticus.runtime._successor import SuccessorIntentStore


class MutableClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


T0 = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


def _store(tmp_path, clock, application='ada', job_key='kpi-runtime'):
    return SuccessorIntentStore(
        volume_path=tmp_path,
        application=application,
        job_key=job_key,
        clock=clock,
    )


def test_successor_announces_and_previous_slot_detects_it(tmp_path):
    clock = MutableClock(T0)
    owner = _store(tmp_path, clock)
    successor = _store(tmp_path, clock)
    assert owner.read() is None
    assert successor.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=1200)

    pending = owner.pending_for(run_id='a', scheduled_at_utc=T0)
    assert pending is not None and pending.run_id == 'b'
    assert pending.expires_at_utc == T0 + timedelta(minutes=20)
    assert successor.pending_for(run_id='b', scheduled_at_utc=T0) is None
    assert owner.pending_for(run_id='a', scheduled_at_utc=T0 + timedelta(minutes=10)) is None
    assert owner.pending_for(run_id='a', scheduled_at_utc=T0 + timedelta(minutes=20)) is None


def test_older_intent_never_overwrites_a_newer_slot(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    assert store.announce(run_id='c', scheduled_at_utc=T0 + timedelta(minutes=20), ttl_seconds=1200)
    clock.at = T0 + timedelta(seconds=3)
    assert not store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=1200)
    assert store.read().run_id == 'c'
    assert not store.clear(run_id='b')
    assert store.read().run_id == 'c'


def test_only_the_current_requester_can_clear_latest_intent(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    assert store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=1200)
    clock.at = T0 + timedelta(seconds=1)
    assert store.announce(run_id='c', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=1200)
    assert not store.clear(run_id='b')
    assert store.read().run_id == 'c'
    assert store.clear(run_id='c')
    assert store.read() is None


def test_expired_intent_does_not_block_future_successor(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    assert store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=5)
    clock.at = T0 + timedelta(seconds=6)
    assert store.read() is None
    assert store.pending_for(run_id='a', scheduled_at_utc=T0) is None
    assert not store.clear(run_id='b')
    assert store.announce(run_id='c', scheduled_at_utc=T0 + timedelta(minutes=20), ttl_seconds=30)
    assert store.read().run_id == 'c'


def test_same_run_id_announcement_is_idempotent(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    scheduled = T0 + timedelta(minutes=10)
    assert store.announce(run_id='b', scheduled_at_utc=scheduled, ttl_seconds=30)
    before = store.path.read_bytes()
    clock.at = T0 + timedelta(seconds=4)
    assert store.announce(run_id='b', scheduled_at_utc=scheduled, ttl_seconds=30)
    assert store.path.read_bytes() == before


def test_intents_are_isolated_by_application_and_job_key(tmp_path):
    clock = MutableClock(T0)
    first = _store(tmp_path, clock)
    second_app = _store(tmp_path, clock, application='other')
    second_key = _store(tmp_path, clock, job_key='historian')
    assert first.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=30)
    assert second_app.read() is None
    assert second_key.read() is None


def test_concurrent_announcements_preserve_latest_scheduled_slot(tmp_path):
    clock = MutableClock(T0)
    def announce(index):
        return _store(tmp_path, clock).announce(
            run_id=f'run-{index}',
            scheduled_at_utc=T0 + timedelta(minutes=index * 10),
            ttl_seconds=1200,
        )
    with ThreadPoolExecutor(max_workers=6) as workers:
        list(workers.map(announce, (1, 3, 2, 5, 4, 6)))
    intent = _store(tmp_path, clock).read()
    assert intent is not None
    assert intent.run_id == 'run-6'
    assert intent.scheduled_at_utc == T0 + timedelta(minutes=60)


def test_corrupted_signal_fails_closed(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    assert store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=30)
    store.path.write_text('{invalid', encoding='utf-8')
    with pytest.raises(AtlanticusRuntimeError, match='unreadable'):
        store.read()
    with pytest.raises(AtlanticusRuntimeError, match='unreadable'):
        store.announce(run_id='c', scheduled_at_utc=T0 + timedelta(minutes=20), ttl_seconds=30)


def test_invalid_shape_and_non_utc_dates_are_rejected(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    with pytest.raises(ValueError, match='greater than zero'):
        store.announce(run_id='b', scheduled_at_utc=T0, ttl_seconds=0)
    with pytest.raises(ValueError, match='greater than zero'):
        store.announce(run_id='b', scheduled_at_utc=T0, ttl_seconds=float('nan'))
    with pytest.raises(TypeError, match='number'):
        store.announce(run_id='b', scheduled_at_utc=T0, ttl_seconds=True)
    with pytest.raises(ValueError, match='UTC'):
        store.announce(run_id='b', scheduled_at_utc=T0.replace(tzinfo=None), ttl_seconds=30)
    with pytest.raises(ValueError, match='nonempty'):
        store.announce(run_id=' ', scheduled_at_utc=T0, ttl_seconds=30)
    assert store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=30)
    payload = json.loads(store.path.read_text(encoding='utf-8'))
    payload['schema_version'] = 2
    store.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(AtlanticusRuntimeError, match='invalid'):
        store.read()
    payload['schema_version'] = True
    store.path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(AtlanticusRuntimeError, match='invalid'):
        store.read()


def test_lease_file_is_not_modified_by_successor_intents(tmp_path):
    clock = MutableClock(T0)
    store = _store(tmp_path, clock)
    lease_path = tmp_path / 'ada' / '.runtime' / 'leases' / 'kpi-runtime.json'
    lease_path.parent.mkdir(parents=True)
    lease_path.write_text('{"owner_token":"original"}', encoding='utf-8')
    assert store.announce(run_id='b', scheduled_at_utc=T0 + timedelta(minutes=10), ttl_seconds=30)
    assert store.clear(run_id='b')
    assert lease_path.read_text(encoding='utf-8') == '{"owner_token":"original"}'
