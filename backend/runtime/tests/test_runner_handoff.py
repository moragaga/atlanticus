from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration, execute_job
from atlanticus.runtime._successor import SuccessorIntentStore
from atlanticus.runtime._window import build_execution_window
from atlanticus.runtime.errors import RuntimeContractError
from atlanticus.runtime.lease import ExecutionLease


def _definition(*, run_once: bool = False, poll: float = 0.0) -> JobDefinition:
    return JobDefinition(
        module_name='handoff_test',
        service_name='handoff-test',
        job_key='handoff-test',
        run_once=run_once,
        poll_interval_seconds=poll,
        iteration_timeout_seconds=10,
        execution_timeout_seconds=300,
        shutdown_grace_seconds=5,
        lease_timeout_seconds=120,
        lease_poll_seconds=0.01,
        resource_sample_seconds=0.01,
    )


def _environment(tmp_path, *, scheduled: bool = True) -> dict[str, str]:
    result = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada',
        'VOLUMEN_PATH': str(tmp_path),
    }
    if scheduled:
        result['ATLANTICUS_JOB_SCHEDULE_CRON'] = '* * * * *'
        result['ATLANTICUS_JOB_SCHEDULE_TIMEZONE'] = 'UTC'
    return result


@pytest.mark.parametrize('value', [True, -0.01, float('nan'), float('inf'), '2'])
def test_poll_interval_rejects_invalid_configuration_types(value) -> None:
    with pytest.raises((TypeError, RuntimeContractError)):
        JobDefinition(module_name='test_job', service_name='test-job', poll_interval_seconds=value)


def test_zero_poll_interval_is_supported() -> None:
    assert _definition(poll=0.0).poll_interval_seconds == 0.0


def test_old_sleep_contract_is_not_retained() -> None:
    with pytest.raises(TypeError):
        JobDefinition(module_name='test_job', service_name='test-job', sleep_seconds=1)


def test_scheduled_handoff_extends_window_to_one_additional_cron_cycle(tmp_path) -> None:
    configuration = RuntimeConfiguration.from_sources(environ=_environment(tmp_path))
    t0 = datetime(2026, 10, 16, 10, 0, 5, tzinfo=UTC)
    definition = _definition()
    handoff = build_execution_window(
        definition=definition,
        configuration=configuration,
        started_at_utc=t0,
        started_monotonic=100.0,
        successor_handoff=True,
    )
    bounded = build_execution_window(
        definition=_definition(run_once=True),
        configuration=configuration,
        started_at_utc=t0,
        started_monotonic=100.0,
    )
    assert handoff.next_scheduled_at_utc == t0.replace(minute=1, second=0)
    assert handoff.deadline_utc == t0.replace(minute=2, second=0)
    assert handoff.safe_deadline_utc > handoff.next_scheduled_at_utc
    assert bounded.deadline_utc == t0 + timedelta(seconds=300)


def test_relative_execution_waits_full_post_iteration_poll(tmp_path, monkeypatch) -> None:
    observed: list[float] = []
    original = JobRuntimeContext.wait

    def capture(self: JobRuntimeContext, seconds: float) -> bool:
        observed.append(seconds)
        return original(self, seconds)

    monkeypatch.setattr(JobRuntimeContext, 'wait', capture)

    def iteration(context: JobRuntimeContext) -> None:
        time.sleep(0.03)
        if context.iteration == 2:
            context.request_stop('requested')

    result = execute_job(
        definition=_definition(poll=0.2),
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path, scheduled=False),
    )
    assert result.iteration_count == 2
    assert result.stop_reason == 'requested'
    assert observed == [pytest.approx(0.2)]


def test_scheduled_owner_yields_after_full_iteration(tmp_path) -> None:
    seen = []

    def iteration(context: JobRuntimeContext) -> None:
        seen.append(context.iteration)
        assert context.scheduled_at_utc is not None
        assert context.next_scheduled_at_utc is not None
        store = SuccessorIntentStore(
            volume_path=context.volume_path,
            application=context.application,
            job_key=context.definition.job_key,
            clock=context._utc_now,
        )
        assert store.announce(
            run_id='successor-b',
            scheduled_at_utc=context.next_scheduled_at_utc,
            ttl_seconds=200,
        )

    result = execute_job(
        definition=_definition(),
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path),
    )
    assert seen == [1]
    assert result.stop_reason == 'successor_ready'
    assert result.iteration_count == 1


def test_successor_arrival_interrupts_poll_wait(tmp_path, monkeypatch) -> None:
    waiting = []

    def fake_wait(context: JobRuntimeContext, seconds: float) -> bool:
        waiting.append(seconds)
        if len(waiting) == 1:
            store = SuccessorIntentStore(
                volume_path=context.volume_path,
                application=context.application,
                job_key=context.definition.job_key,
                clock=context._utc_now,
            )
            assert store.announce(
                run_id='successor-c',
                scheduled_at_utc=context.next_scheduled_at_utc,
                ttl_seconds=200,
            )
        return True

    monkeypatch.setattr(JobRuntimeContext, 'wait', fake_wait)
    result = execute_job(
        definition=_definition(poll=30),
        iteration=lambda context: None,
        argv=[],
        environ=_environment(tmp_path),
    )
    assert result.iteration_count == 1
    assert result.stop_reason == 'successor_ready'
    assert waiting == [pytest.approx(0.01)]


def test_debug_and_run_once_do_not_publish_handoff(tmp_path, monkeypatch) -> None:
    published: list[str] = []
    original = ExecutionLease.announce_successor

    def observe(self, *, ttl_seconds: float) -> bool:
        published.append('published')
        return original(self, ttl_seconds=ttl_seconds)

    monkeypatch.setattr(ExecutionLease, 'announce_successor', observe)
    monkeypatch.setattr(
        'atlanticus.runtime.context._utc_now',
        lambda: datetime(2026, 10, 16, 10, 0, 5, tzinfo=UTC),
    )
    for args in (['--run-once'], ['--debug']):
        result = execute_job(
            definition=_definition(),
            iteration=lambda context: None,
            argv=args,
            environ=_environment(tmp_path / ('once' if args[0] == '--run-once' else 'debug')),
        )
        assert result.iteration_count == 1
        assert result.stop_reason == 'run_once'
    assert published == []
