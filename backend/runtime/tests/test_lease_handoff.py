from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.runtime.errors import AtlanticusRuntimeError, ConcurrentExecutionError
from atlanticus.runtime.lease import ExecutionLease


T0 = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def lease(
    tmp_path,
    name: str,
    clock: Clock,
    slot: int | None,
    handoff: bool = True,
    *,
    wait_seconds: float = 0,
):
    return ExecutionLease(
        volume_path=tmp_path,
        application='ada',
        service_name='kpi-runtime',
        module_name='kpi_runtime',
        job_key='kpi-runtime',
        run_id=name,
        scheduled_at_utc=None if slot is None else T0 + timedelta(minutes=slot),
        successor_handoff=handoff,
        wall_clock=clock,
        lease_timeout_seconds=120,
        wait_seconds=wait_seconds,
        poll_seconds=0.01,
        instance_id=f'instance-{name}',
        process_id=101,
    )


def test_signal_is_visible_to_owner_without_changing_lease(tmp_path) -> None:
    clock = Clock(T0)
    owner = lease(tmp_path, 'a', clock, 0)
    successor = lease(tmp_path, 'b', clock, 10)
    assert owner.acquire().acquired
    original = owner.path.read_bytes()
    assert successor.announce_successor(ttl_seconds=300)
    assert owner.path.read_bytes() == original
    intent = owner.pending_successor()
    assert intent is not None and intent.run_id == 'b'
    with pytest.raises(ConcurrentExecutionError):
        successor.acquire()
    assert owner.release()
    assert successor.acquire().acquired
    assert successor.clear_successor()
    assert successor.pending_successor() is None
    assert successor.release()


def test_newer_successor_supersedes_waiting_candidate_before_acquisition(tmp_path) -> None:
    clock = Clock(T0)
    owner = lease(tmp_path, 'a', clock, 0)
    second = lease(tmp_path, 'b', clock, 10)
    third = lease(tmp_path, 'c', clock, 20)
    assert owner.acquire().acquired
    assert second.announce_successor(ttl_seconds=500)
    assert third.announce_successor(ttl_seconds=500)
    assert owner.pending_successor().run_id == 'c'
    assert not second.clear_successor()
    assert owner.release()
    acquisition = second.acquire()
    assert not acquisition.acquired
    assert acquisition.skipped_reason == 'successor_superseded'
    assert not second.acquired
    assert third.acquire().acquired
    assert third.clear_successor()
    assert third.release()


def test_newer_retry_in_same_scheduled_slot_preempts_old_requester(tmp_path) -> None:
    clock = Clock(T0)
    prior = lease(tmp_path, 'previous-attempt', clock, 10)
    current = lease(tmp_path, 'retry', clock, 10)
    assert prior.announce_successor(ttl_seconds=500)
    clock.at += timedelta(seconds=1)
    assert current.announce_successor(ttl_seconds=500)
    acquisition = prior.acquire()
    assert acquisition.skipped_reason == 'successor_superseded'
    assert current.acquire().acquired
    assert current.clear_successor()
    assert current.release()


def test_older_slot_cannot_reacquire_while_newer_request_is_ready(tmp_path) -> None:
    clock = Clock(T0)
    prior = lease(tmp_path, 'old', clock, 0)
    successor = lease(tmp_path, 'new', clock, 10)
    assert successor.announce_successor(ttl_seconds=50)
    assert prior.acquire().skipped_reason == 'successor_superseded'
    assert successor.acquire().acquired
    assert successor.release()


def test_expired_signal_does_not_block_normal_acquisition(tmp_path) -> None:
    clock = Clock(T0)
    stale = lease(tmp_path, 'stale', clock, 10)
    older = lease(tmp_path, 'old', clock, 0)
    assert stale.announce_successor(ttl_seconds=5)
    clock.at += timedelta(seconds=6)
    assert older.acquire().acquired
    assert older.pending_successor() is None
    assert older.release()


def test_manual_and_existing_lease_behavior_remain_opt_out(tmp_path) -> None:
    clock = Clock(T0)
    manual = lease(tmp_path, 'manual', clock, None, False)
    scheduled = lease(tmp_path, 'scheduled', clock, 10, False)
    assert manual.acquire().acquired
    assert manual.pending_successor() is None
    with pytest.raises(ValueError, match='not enabled'):
        manual.announce_successor(ttl_seconds=60)
    assert manual.clear_successor() is False
    assert manual.release()
    assert scheduled.acquire().acquired
    assert scheduled.release()


def test_handoff_requires_scheduled_slot_and_boolean_opt_in(tmp_path) -> None:
    clock = Clock(T0)
    with pytest.raises(ValueError, match='requires scheduled_at_utc'):
        lease(tmp_path, 'bad', clock, None, True)
    with pytest.raises(TypeError, match='must be a bool'):
        lease(tmp_path, 'bad', clock, 10, 'yes')


def test_corrupted_successor_marker_fails_closed_before_authority_creation(tmp_path) -> None:
    clock = Clock(T0)
    old = lease(tmp_path, 'old', clock, 0)
    newer = lease(tmp_path, 'new', clock, 10)
    assert newer.announce_successor(ttl_seconds=50)
    newer.successor_path.write_text('not JSON', encoding='utf-8')
    with pytest.raises(AtlanticusRuntimeError, match='unreadable'):
        old.acquire()
    assert not old.path.exists()
    assert not old.authority_path.exists()


def test_disabled_handoff_ignores_marker_and_retains_prior_contract(tmp_path) -> None:
    clock = Clock(T0)
    disabled = lease(tmp_path, 'old', clock, 0, False)
    successor = lease(tmp_path, 'b', clock, 10)
    assert successor.announce_successor(ttl_seconds=200)
    assert disabled.acquire().acquired
    assert disabled.pending_successor() is None
    assert disabled.release()


def test_handoff_only_mutates_signal_and_durable_authority_on_acquisition(tmp_path) -> None:
    clock = Clock(T0)
    successor = lease(tmp_path, 'b', clock, 10)
    assert successor.announce_successor(ttl_seconds=500)
    assert not successor.path.exists()
    assert not successor.authority_path.exists()
    assert successor.acquire().acquired
    assert successor.authority_path.exists()
    assert successor.clear_successor()
    assert successor.release()
    data = json.loads(successor.authority_path.read_text(encoding='utf-8'))
    assert data['generation'] == 1


def test_concurrent_waiters_respect_current_successor_priority(tmp_path) -> None:
    clock = Clock(T0)
    first = lease(tmp_path, 'b', clock, 10, wait_seconds=2.0)
    second = lease(tmp_path, 'c', clock, 20, wait_seconds=2.0)
    assert first.announce_successor(ttl_seconds=500)
    assert second.announce_successor(ttl_seconds=500)
    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(first.acquire)
        right = pool.submit(second.acquire)
        first_result = left.result()
        second_result = right.result()
    assert first_result.skipped_reason == 'successor_superseded'
    assert second_result.acquired
    assert second.release()
