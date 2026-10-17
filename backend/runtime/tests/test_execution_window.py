from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from atlanticus.runtime import JobDefinition, JobRuntimeContext, RuntimeConfiguration


def _definition() -> JobDefinition:
    return JobDefinition(
        module_name='runtime.job',
        service_name='runtime-job',
        run_once=True,
        iteration_timeout_seconds=60,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=20,
        lease_timeout_seconds=120,
    )


def _configuration(tmp_path, **values: str) -> RuntimeConfiguration:
    return RuntimeConfiguration.from_sources(
        environ={
            'ENVIRONMENT': 'local',
            'APPLICATION': 'ada',
            'VOLUMEN_PATH': str(tmp_path),
            **values,
        }
    )


def test_relative_mode_uses_runtime_execution_budget(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=_definition(),
        configuration=_configuration(tmp_path),
        run_id='run-1',
        correlation_id='correlation-1',
        clock=lambda: 100.0,
        wall_clock=lambda: datetime(2026, 8, 23, 21, 16, 0, tzinfo=UTC),
    )

    assert context.execution_mode == 'relative'
    assert context.scheduled_at_utc is None
    assert context.deadline_monotonic == 700
    assert context.safe_deadline_monotonic == 680
    assert context.deadline_utc == datetime(2026, 8, 23, 21, 26, 0, tzinfo=UTC)


def test_scheduled_run_once_keeps_slot_identity_but_uses_timeout(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=_definition(),
        configuration=_configuration(
            tmp_path,
            ATLANTICUS_JOB_SCHEDULE_CRON='*/10 * * * *',
            ATLANTICUS_JOB_SCHEDULE_TIMEZONE='UTC',
        ),
        run_id='run-1',
        correlation_id='correlation-1',
        clock=lambda: 100.0,
        wall_clock=lambda: datetime(2026, 8, 23, 21, 16, 0, tzinfo=UTC),
    )

    assert context.execution_mode == 'scheduled_external'
    assert context.scheduled_at_utc == datetime(2026, 8, 23, 21, 10, 0, tzinfo=UTC)
    assert context.next_scheduled_at_utc == datetime(2026, 8, 23, 21, 20, 0, tzinfo=UTC)
    assert context.deadline_utc == datetime(2026, 8, 23, 21, 26, 0, tzinfo=UTC)
    assert context.safe_deadline_utc == datetime(2026, 8, 23, 21, 25, 40, tzinfo=UTC)
    assert context.deadline_monotonic == 700
    assert context.safe_deadline_monotonic == 680


def test_platform_timeout_can_be_the_most_restrictive_boundary(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=_definition(),
        configuration=_configuration(
            tmp_path,
            ATLANTICUS_JOB_SCHEDULE_CRON='0 */2 * * *',
            ATLANTICUS_JOB_SCHEDULE_TIMEZONE='UTC',
            ATLANTICUS_JOB_PLATFORM_TIMEOUT_SECONDS='300',
        ),
        run_id='run-1',
        correlation_id='correlation-1',
        clock=lambda: 500.0,
        wall_clock=lambda: datetime(2026, 8, 23, 10, 0, 0, tzinfo=UTC),
    )

    assert context.scheduled_at_utc == datetime(2026, 8, 23, 10, 0, 0, tzinfo=UTC)
    assert context.next_scheduled_at_utc == datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    assert context.platform_deadline_utc == datetime(2026, 8, 23, 10, 5, 0, tzinfo=UTC)
    assert context.deadline_utc == datetime(2026, 8, 23, 10, 5, 0, tzinfo=UTC)
    assert context.safe_deadline_utc == datetime(2026, 8, 23, 10, 4, 40, tzinfo=UTC)
    assert context.deadline_monotonic == 800
    assert context.safe_deadline_monotonic == 780


def test_scheduled_continuous_uses_following_cron_slot_not_execution_seconds(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=replace(_definition(), run_once=False),
        configuration=_configuration(
            tmp_path,
            ATLANTICUS_JOB_SCHEDULE_CRON='*/10 * * * *',
            ATLANTICUS_JOB_SCHEDULE_TIMEZONE='UTC',
        ),
        run_id='run-2',
        correlation_id='correlation-2',
        clock=lambda: 100.0,
        wall_clock=lambda: datetime(2026, 10, 16, 20, 50, 5, tzinfo=UTC),
        successor_handoff=True,
    )

    assert context.execution_mode == 'scheduled_external'
    assert context.scheduled_at_utc == datetime(2026, 10, 16, 20, 50, tzinfo=UTC)
    assert context.next_scheduled_at_utc == datetime(2026, 10, 16, 21, 0, tzinfo=UTC)
    assert context.deadline_utc == datetime(2026, 10, 16, 21, 10, tzinfo=UTC)
    assert context.safe_deadline_utc == datetime(2026, 10, 16, 21, 9, 40, tzinfo=UTC)
    assert context.deadline_monotonic == 1295
    assert context.safe_deadline_monotonic == 1275


def test_scheduled_continuous_uses_real_non_uniform_cron_occurrences(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=replace(_definition(), run_once=False),
        configuration=_configuration(
            tmp_path,
            ATLANTICUS_JOB_SCHEDULE_CRON='0 10,11,13 * * *',
            ATLANTICUS_JOB_SCHEDULE_TIMEZONE='UTC',
        ),
        run_id='run-3',
        correlation_id='correlation-3',
        clock=lambda: 100.0,
        wall_clock=lambda: datetime(2026, 10, 16, 10, 0, 5, tzinfo=UTC),
        successor_handoff=True,
    )

    assert context.scheduled_at_utc == datetime(2026, 10, 16, 10, 0, tzinfo=UTC)
    assert context.next_scheduled_at_utc == datetime(2026, 10, 16, 11, 0, tzinfo=UTC)
    assert context.deadline_utc == datetime(2026, 10, 16, 13, 0, tzinfo=UTC)


def test_scheduled_continuous_respects_physical_platform_limit(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=replace(_definition(), run_once=False),
        configuration=_configuration(
            tmp_path,
            ATLANTICUS_JOB_SCHEDULE_CRON='*/10 * * * *',
            ATLANTICUS_JOB_SCHEDULE_TIMEZONE='UTC',
            ATLANTICUS_JOB_PLATFORM_TIMEOUT_SECONDS='900',
        ),
        run_id='run-4',
        correlation_id='correlation-4',
        clock=lambda: 100.0,
        wall_clock=lambda: datetime(2026, 10, 16, 20, 50, 5, tzinfo=UTC),
        successor_handoff=True,
    )

    assert context.platform_deadline_utc == datetime(2026, 10, 16, 21, 5, 5, tzinfo=UTC)
    assert context.deadline_utc == context.platform_deadline_utc
    assert context.safe_deadline_utc == datetime(2026, 10, 16, 21, 4, 45, tzinfo=UTC)
