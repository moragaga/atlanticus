from __future__ import annotations

import json
import signal
from datetime import UTC, datetime, timedelta

import pytest

import atlanticus.runtime.context as context_module
import atlanticus.runtime.runner as runner_module
from atlanticus.kernel import OperationStatus
from atlanticus.observability import configure_volume_observability
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    LeaseOwnershipLostError,
    RuntimeCancellationRequested,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.runtime._fence import PhysicalAuthorityFence
from atlanticus.runtime._resource_sampler import CgroupResourceSampler
from atlanticus.runtime.lease import ExecutionLease, LeaseAcquisition


def _definition(*, service_name: str = 'dispatch-ingestion-job') -> JobDefinition:
    return JobDefinition(
        module_name='dispatch_ingestion',
        service_name=service_name,
        run_once=True,
        iteration_timeout_seconds=5,
        execution_timeout_seconds=10,
        shutdown_grace_seconds=2,
        lease_timeout_seconds=12,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )


def _environment(tmp_path, environment='local') -> dict[str, str]:
    return {
        'ENVIRONMENT': environment,
        'APPLICATION': 'ada',
        'VOLUMEN_PATH': str(tmp_path),
    }


def _day_directory(tmp_path, service_name: str = 'dispatch-ingestion-job'):
    day = datetime.now(UTC).date().isoformat()
    return tmp_path / 'ada' / 'logs' / service_name / f'day={day}'


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('run_id', 'not-a-uuid'),
        ('correlation_id', 'not-a-uuid'),
        ('status', 'success'),
        ('iteration_count', True),
        ('duration_seconds', float('nan')),
        ('stop_reason', 'Not valid'),
    ],
)
def test_execution_result_rejects_invalid_direct_contract(field, value) -> None:
    values = {
        'run_id': '4af45e0b-bdde-4125-96f2-89aa7452dd64',
        'correlation_id': 'c5150d54-1f4f-4d62-b52c-0bc3eaeb1191',
        'status': OperationStatus.SUCCESS,
        'iteration_count': 1,
        'duration_seconds': 1.0,
        'stop_reason': 'completed',
        field: value,
    }

    with pytest.raises((TypeError, ValueError)):
        RuntimeExecutionResult(**values)


@pytest.mark.parametrize(
    ('definition_values', 'expected_wait'),
    [
        (
            {
                'lease_timeout_seconds': 20,
                'lease_poll_seconds': 1,
                'lease_wait_seconds': None,
            },
            21,
        ),
        ({'lease_wait_seconds': 90}, 50),
    ],
)
def test_execute_job_bounds_lease_wait_by_available_budget(
    tmp_path,
    monkeypatch,
    definition_values,
    expected_wait,
) -> None:
    captured_wait: list[float] = []

    def fake_acquire(self) -> LeaseAcquisition:
        captured_wait.append(self._wait_seconds)
        self._acquired = True
        acquisition = LeaseAcquisition(waited_seconds=0)
        self._acquisition = acquisition
        return acquisition

    monkeypatch.setattr(ExecutionLease, 'acquire', fake_acquire)
    monkeypatch.setattr(ExecutionLease, 'assert_current', lambda self: None)
    monkeypatch.setattr(ExecutionLease, 'start_renewal', lambda self, on_lost=None: None)
    monkeypatch.setattr(ExecutionLease, 'release', lambda self, completed=False: True)

    definition = JobDefinition(
        module_name='job',
        service_name='budget-job',
        run_once=True,
        execution_timeout_seconds=60,
        shutdown_grace_seconds=10,
        iteration_timeout_seconds=20,
        resource_sample_seconds=1,
        **definition_values,
    )

    execute_job(
        definition=definition,
        iteration=lambda context: None,
        argv=[],
        environ=_environment(tmp_path, environment='dev'),
    )

    assert len(captured_wait) == 1
    assert captured_wait[0] == pytest.approx(expected_wait, abs=0.01)


def test_lease_wait_consumes_execution_budget(tmp_path, monkeypatch) -> None:
    now = [100.0]
    captured_wait: list[float] = []
    observed_remaining: list[float] = []

    def fake_monotonic() -> float:
        return now[0]

    def fake_acquire(self) -> LeaseAcquisition:
        captured_wait.append(self._wait_seconds)
        now[0] += 20
        self._acquired = True
        acquisition = LeaseAcquisition(waited_seconds=20)
        self._acquisition = acquisition
        return acquisition

    monkeypatch.setattr(runner_module.time, 'monotonic', fake_monotonic)
    monkeypatch.setattr(ExecutionLease, 'acquire', fake_acquire)
    monkeypatch.setattr(ExecutionLease, 'assert_current', lambda self: None)
    monkeypatch.setattr(ExecutionLease, 'start_renewal', lambda self, on_lost=None: None)
    monkeypatch.setattr(ExecutionLease, 'release', lambda self, completed=False: True)

    definition = JobDefinition(
        module_name='job',
        service_name='budget-job',
        run_once=True,
        execution_timeout_seconds=60,
        shutdown_grace_seconds=10,
        iteration_timeout_seconds=20,
        lease_wait_seconds=None,
        resource_sample_seconds=1,
    )

    def iteration(context) -> None:
        observed_remaining.append(context.safe_remaining_seconds)
        now[0] += 1

    result = execute_job(
        definition=definition,
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path, environment='dev'),
    )

    assert captured_wait == [50]
    assert observed_remaining == [30]
    assert result.duration_seconds == 21


def test_runtime_projects_only_azure_observability_environment(tmp_path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def configure(settings, *, environ) -> None:
        captured.update(environ)
        configure_volume_observability(settings=settings, include_console=False)

    monkeypatch.setattr(runner_module, '_configure_runtime_observability', configure)
    environment = {
        **_environment(tmp_path, environment='dev'),
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
        'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
        'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=secret',
        'COSMOS_KEY_OPERATIONAL': 'must-not-be-projected',
    }

    execute_job(
        definition=_definition(),
        iteration=lambda context: None,
        argv=[],
        environ=environment,
    )

    assert captured == {
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
        'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'diagnostic',
        'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=secret',
    }


def test_execute_job_writes_work_iteration_and_execution_summary(tmp_path, capsys) -> None:
    def iteration(context) -> None:
        context.mark_iteration_work()
        context.set_iteration_fact('table', 'std_shift_dumps')
        context.set_iteration_fact('new_data', True)
        context.set_execution_fact('new_data', True)
        context.increment_execution_counter('rows', 120)

    result = execute_job(
        definition=_definition(),
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path),
    )

    directory = _day_directory(tmp_path)
    iterations = [
        json.loads(line) for line in (directory / 'iterations.jsonl').read_text().splitlines()
    ]
    executions = [
        json.loads(line) for line in (directory / 'executions.jsonl').read_text().splitlines()
    ]
    console = capsys.readouterr().out

    assert result.iteration_count == 1
    assert len(iterations) == 1
    assert iterations[0]['event'] == 'iteration.completed'
    assert iterations[0]['table'] == 'std_shift_dumps'
    assert len(executions) == 1
    assert executions[0]['event'] == 'execution.completed'
    assert executions[0]['work_iterations'] == 1
    assert executions[0]['empty_iterations'] == 0
    assert executions[0]['rows'] == 120
    assert 'dispatch-ingestion-job started' in console
    assert 'dispatch-ingestion-job completed' in console
    assert 'new_data=true' in console
    assert '"context"' not in console
    assert not (directory / 'events.jsonl').exists()
    assert not (tmp_path / 'ada' / '.runtime' / 'leases' / 'dispatch-ingestion-job.json').exists()


def test_empty_iteration_is_counted_without_iteration_record(tmp_path) -> None:
    execute_job(
        definition=_definition(),
        iteration=lambda context: None,
        argv=[],
        environ=_environment(tmp_path, environment='dev'),
    )

    directory = _day_directory(tmp_path)
    assert not (directory / 'iterations.jsonl').exists()
    execution = json.loads((directory / 'executions.jsonl').read_text().splitlines()[0])
    assert execution['work_iterations'] == 0
    assert execution['empty_iterations'] == 1


def test_preview_contains_the_operational_log_contract(tmp_path) -> None:
    environment = {
        **_environment(tmp_path, environment='dev'),
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'preview',
        'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
    }

    def iteration(context) -> None:
        context.mark_iteration_work()
        context.set_iteration_fact('rows', 25)
        context.increment_execution_counter('rows', 25)

    execute_job(
        definition=_definition(),
        iteration=iteration,
        argv=[],
        environ=environment,
    )

    records = [
        json.loads(line)
        for line in (_day_directory(tmp_path) / 'azure-preview.jsonl').read_text().splitlines()
    ]
    assert [record['event'] for record in records] == [
        'execution.started',
        'iteration.completed',
        'execution.completed',
    ]
    assert records[0]['application'] == 'ada'
    assert records[0]['environment'] == 'dev'
    assert records[1]['rows'] == 25
    assert records[2]['rows'] == 25


def test_invalid_azure_configuration_becomes_warning_and_job_continues(tmp_path) -> None:
    environment = _environment(tmp_path, environment='dev')
    environment['ATLANTICUS_AZURE_OBSERVABILITY_MODE'] = 'export'

    result = execute_job(
        definition=_definition(),
        iteration=lambda context: None,
        argv=[],
        environ=environment,
    )

    issues = [
        json.loads(line)
        for line in (_day_directory(tmp_path) / 'issues.jsonl').read_text().splitlines()
    ]
    assert result.status is OperationStatus.SUCCESS
    assert issues[0]['event'] == 'observability.azure.bootstrap.failed'
    assert issues[0]['level'] == 'warning'
    assert issues[0]['error_type']


def test_recovered_lease_records_previous_execution_timeout(tmp_path, capsys) -> None:
    definition = _definition()
    stale = ExecutionLease(
        volume_path=tmp_path,
        application='ada',
        service_name=definition.service_name,
        module_name=definition.module_name,
        run_id='previous-run',
        lease_timeout_seconds=12,
        wait_seconds=0,
    )
    stale.acquire()
    payload = json.loads(stale.path.read_text())
    payload['expires_at_utc'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    stale.path.write_text(json.dumps(payload))

    execute_job(
        definition=definition,
        iteration=lambda context: None,
        argv=[],
        environ=_environment(tmp_path),
    )
    capsys.readouterr()

    executions = [
        json.loads(line)
        for line in (_day_directory(tmp_path) / 'executions.jsonl').read_text().splitlines()
    ]
    assert executions[0]['event'] == 'execution.timed_out'
    assert executions[0]['run_id'] == 'previous-run'
    assert executions[1]['event'] == 'execution.completed'


def test_failed_iteration_records_sanitized_failure_with_diagnostic_reference(
    tmp_path,
    capsys,
) -> None:
    signed_url = 'https://account.blob.core.windows.net/data?sig=secret-value'

    def fail(context) -> None:
        raise ValueError(signed_url)

    with pytest.raises(ValueError, match='secret-value'):
        execute_job(
            definition=_definition(),
            iteration=fail,
            argv=[],
            environ=_environment(tmp_path),
        )
    console = capsys.readouterr().err

    execution = json.loads(
        (_day_directory(tmp_path) / 'executions.jsonl').read_text().splitlines()[0]
    )
    issue = json.loads((_day_directory(tmp_path) / 'issues.jsonl').read_text().splitlines()[0])
    assert execution['event'] == 'execution.failed'
    assert execution['error_type'] == 'ValueError'
    assert execution['diagnostic_available'] is True
    assert execution['failed_iteration'] == 1
    assert issue['traceback']
    assert signed_url not in console
    assert signed_url not in json.dumps(execution)
    assert signed_url not in json.dumps(issue)
    assert not (tmp_path / 'ada/.runtime/leases/dispatch-ingestion-job.json').exists()


@pytest.mark.parametrize(
    ('error_factory', 'expected_reason'),
    [
        (lambda: KeyboardInterrupt(), 'interrupted'),
        (lambda: RuntimeCancellationRequested('requested'), 'requested'),
    ],
)
def test_controlled_cancellation_is_not_recorded_as_failure(
    tmp_path,
    error_factory,
    expected_reason,
) -> None:
    def cancel(context) -> None:
        raise error_factory()

    result = execute_job(
        definition=_definition(),
        iteration=cancel,
        argv=[],
        environ=_environment(tmp_path, environment='dev'),
    )

    execution = json.loads(
        (_day_directory(tmp_path) / 'executions.jsonl').read_text().splitlines()[0]
    )
    assert result.status is OperationStatus.WARNING
    assert result.stop_reason == expected_reason
    assert execution['event'] == 'execution.cancelled'
    assert execution['stop_reason'] == expected_reason
    assert not (_day_directory(tmp_path) / 'issues.jsonl').exists()


def test_sigterm_drains_before_heartbeat_stops_and_restores_handler(tmp_path, monkeypatch) -> None:
    lifecycle: list[str] = []
    lease_holder: list[ExecutionLease] = []
    previous_handler = signal.getsignal(signal.SIGTERM)
    original_start = ExecutionLease.start_renewal
    original_stop = ExecutionLease.stop_renewal

    def tracking_start(self, *, on_lost=None) -> None:
        lease_holder.append(self)
        original_start(self, on_lost=on_lost)

    def tracking_stop(self) -> None:
        lifecycle.append('stop_renewal')
        original_stop(self)

    monkeypatch.setattr(ExecutionLease, 'start_renewal', tracking_start)
    monkeypatch.setattr(ExecutionLease, 'stop_renewal', tracking_stop)

    def iteration(context: JobRuntimeContext) -> None:
        lifecycle.append('iteration')
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)

    def drain(context: JobRuntimeContext) -> None:
        lifecycle.append('drain')
        assert lease_holder
        thread = lease_holder[0]._renewal_thread
        assert thread is not None and thread.is_alive()
        context.assert_lease_current()

    result = execute_job(
        definition=_definition(service_name='sigterm-drain-job'),
        iteration=iteration,
        drain=drain,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert result.status is OperationStatus.WARNING
    assert result.stop_reason == 'sigterm'
    assert lifecycle[:2] == ['iteration', 'drain']
    assert lifecycle.index('drain') < lifecycle.index('stop_renewal')
    assert signal.getsignal(signal.SIGTERM) == previous_handler


def test_lost_lease_stops_business_and_fails_execution(tmp_path) -> None:
    definition = JobDefinition(
        module_name='lease_loss_job',
        service_name='lease-loss-job',
        run_once=True,
        iteration_timeout_seconds=1,
        execution_timeout_seconds=2,
        shutdown_grace_seconds=0.2,
        lease_timeout_seconds=0.2,
        lease_renew_seconds=0.02,
        lease_wait_seconds=0,
        resource_sample_seconds=0.1,
    )

    def lose_lease(context) -> None:
        path = tmp_path / 'ada' / '.runtime' / 'leases' / 'lease-loss-job.json'
        fence = PhysicalAuthorityFence(
            volume_path=tmp_path,
            application='ada',
            job_key='lease-loss-job',
        )
        descriptor = fence.acquire(wait_seconds=1, poll_seconds=0.01)
        assert descriptor is not None
        try:
            payload = json.loads(path.read_text())
            payload['expires_at_utc'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            path.write_text(json.dumps(payload))
        finally:
            fence.release(descriptor)
        assert not context.wait(1)
        context.raise_if_cancelled()

    with pytest.raises(LeaseOwnershipLostError, match='ownership'):
        execute_job(
            definition=definition,
            iteration=lose_lease,
            argv=[],
            environ=_environment(tmp_path),
        )

    execution = json.loads(
        (_day_directory(tmp_path, 'lease-loss-job') / 'executions.jsonl')
        .read_text()
        .splitlines()[0]
    )
    assert execution['event'] == 'execution.failed'
    assert execution['error_type'] == 'LeaseOwnershipLostError'


def test_release_failure_does_not_hide_business_error(tmp_path, monkeypatch) -> None:
    def fail(context) -> None:
        raise ValueError('business failure')

    def fail_release(self, *, completed: bool = False) -> bool:
        raise OSError('lease cleanup failed')

    monkeypatch.setattr(ExecutionLease, 'release', fail_release)

    with pytest.raises(ValueError, match='business failure'):
        execute_job(
            definition=_definition(),
            iteration=fail,
            argv=[],
            environ=_environment(tmp_path),
        )


def test_resource_sampling_failure_does_not_break_job(tmp_path, monkeypatch) -> None:
    def fail_sample(self):
        raise RuntimeError('sampling failure')

    monkeypatch.setattr(CgroupResourceSampler, 'sample', fail_sample)

    result = execute_job(
        definition=_definition(),
        iteration=lambda context: None,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert result.status is OperationStatus.SUCCESS
    issues = [
        json.loads(line)
        for line in (_day_directory(tmp_path) / 'issues.jsonl').read_text().splitlines()
    ]
    assert issues[0]['event'] == 'resource.monitor.failed'
    assert issues[0]['level'] == 'warning'


def test_iteration_can_override_static_sleep_with_adaptive_delay(tmp_path, monkeypatch) -> None:
    observed_waits: list[float] = []
    iterations: list[int] = []

    def fake_wait(self, seconds: float) -> bool:
        observed_waits.append(seconds)
        return True

    monkeypatch.setattr(JobRuntimeContext, 'wait', fake_wait)

    definition = JobDefinition(
        module_name='adaptive_job',
        service_name='adaptive-job',
        sleep_seconds=5,
        iteration_timeout_seconds=5,
        execution_timeout_seconds=20,
        shutdown_grace_seconds=2,
        lease_timeout_seconds=12,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )

    def iteration(context: JobRuntimeContext) -> None:
        iterations.append(context.iteration)
        if context.iteration == 1:
            context.set_next_iteration_delay(0.25)
            return
        context.request_stop('requested')

    result = execute_job(
        definition=definition,
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert iterations == [1, 2]
    assert observed_waits == [0.25]
    assert result.stop_reason == 'requested'


def test_execute_job_can_disable_file_logs_without_disabling_console(tmp_path, capsys) -> None:
    environment = _environment(tmp_path)
    environment['ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED'] = 'false'

    execute_job(
        definition=_definition(),
        iteration=lambda context: context.mark_iteration_work(),
        argv=[],
        environ=environment,
    )

    console = capsys.readouterr().out
    assert 'dispatch-ingestion-job started' in console
    assert 'dispatch-ingestion-job completed' in console
    assert not (tmp_path / 'ada' / 'logs').exists()


def test_scheduled_run_once_uses_effective_available_window(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        context_module,
        '_utc_now',
        lambda: datetime(2026, 8, 23, 21, 10, 5, tzinfo=UTC),
    )
    observed: list[tuple[str, datetime | None, datetime]] = []
    definition = JobDefinition(
        module_name='scheduled_job',
        service_name='scheduled-job',
        run_once=True,
        iteration_timeout_seconds=60,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=20,
        lease_timeout_seconds=120,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )
    environ = {
        **_environment(tmp_path),
        'ATLANTICUS_JOB_SCHEDULE_CRON': '*/10 * * * *',
        'ATLANTICUS_JOB_PLATFORM_TIMEOUT_SECONDS': '50',
    }

    def iteration(context: JobRuntimeContext) -> None:
        observed.append((context.execution_mode, context.scheduled_at_utc, context.deadline_utc))

    result = execute_job(
        definition=definition,
        iteration=iteration,
        argv=[],
        environ=environ,
    )

    assert result.iteration_count == 1
    assert result.stop_reason == 'run_once'
    assert observed == [
        (
            'scheduled_external',
            datetime(2026, 8, 23, 21, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 23, 21, 10, 55, tzinfo=UTC),
        )
    ]


def test_relative_execution_lease_is_capped_by_execution_deadline(tmp_path) -> None:
    observed: list[tuple[str | None, str]] = []
    definition = JobDefinition(
        module_name='relative_job',
        service_name='relative-job',
        run_once=True,
        iteration_timeout_seconds=5,
        execution_timeout_seconds=10,
        shutdown_grace_seconds=2,
        lease_timeout_seconds=30,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )

    def iteration(context: JobRuntimeContext) -> None:
        payload = json.loads(
            (tmp_path / 'ada/.runtime/leases/relative-job.json').read_text(encoding='utf-8')
        )
        observed.append((payload['authority_deadline_utc'], context.deadline_utc.isoformat()))

    result = execute_job(
        definition=definition,
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert result.stop_reason == 'run_once'
    assert len(observed) == 1
    authority_deadline, context_deadline = observed[0]
    assert authority_deadline == context_deadline


def test_scheduled_slot_is_deduplicated_after_successful_execution(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 23, 21, 10, 5, tzinfo=UTC)
    monkeypatch.setattr(context_module, '_utc_now', lambda: fixed_now)
    definition = JobDefinition(
        module_name='scheduled_job',
        service_name='scheduled-job',
        run_once=True,
        iteration_timeout_seconds=5,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=20,
        lease_timeout_seconds=30,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )
    environment = _environment(tmp_path)
    environment['ATLANTICUS_JOB_SCHEDULE_CRON'] = '*/10 * * * *'
    calls = []

    def iteration(context) -> None:
        calls.append(context.iteration)

    first = execute_job(definition=definition, iteration=iteration, argv=[], environ=environment)
    second = execute_job(definition=definition, iteration=iteration, argv=[], environ=environment)

    assert first.stop_reason == 'run_once'
    assert first.iteration_count == 1
    assert second.stop_reason == 'scheduled_slot_completed'
    assert second.iteration_count == 0
    assert calls == [1]
    authority = json.loads(
        (tmp_path / 'ada/.runtime/authority/scheduled-job.json').read_text(encoding='utf-8')
    )
    assert authority['generation'] == 1
    assert authority['last_completed_scheduled_at_utc'] == '2026-08-23T21:10:00+00:00'


def test_recovery_iteration_and_drain_share_one_lease_generation(tmp_path) -> None:
    order: list[str] = []
    generations: list[int | None] = []

    def recovery(context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        generations.append(context.lease_generation)
        order.append('recovery')
        context.set_memory('recovered', True)

    def iteration(context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        assert context.get_memory('recovered') is True
        generations.append(context.lease_generation)
        order.append('iteration')

    def drain(context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        generations.append(context.lease_generation)
        order.append('drain')

    result = execute_job(
        definition=_definition(service_name='lifecycle-job'),
        recovery=recovery,
        iteration=iteration,
        drain=drain,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert result.status is OperationStatus.SUCCESS
    assert result.iteration_count == 1
    assert order == ['recovery', 'iteration', 'drain']
    assert generations == [1, 1, 1]


def test_recovery_failure_prevents_iteration_and_drain(tmp_path) -> None:
    calls: list[str] = []

    def recovery(context: JobRuntimeContext) -> None:
        calls.append('recovery')
        raise ValueError('recovery failed')

    with pytest.raises(ValueError, match='recovery failed'):
        execute_job(
            definition=_definition(service_name='recovery-failure-job'),
            recovery=recovery,
            iteration=lambda context: calls.append('iteration'),
            drain=lambda context: calls.append('drain'),
            argv=[],
            environ=_environment(tmp_path),
        )

    assert calls == ['recovery']
    assert not (tmp_path / 'ada/.runtime/leases/recovery-failure-job.json').exists()


def test_failed_drain_leaves_scheduled_slot_retriable(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 23, 21, 10, 5, tzinfo=UTC)
    monkeypatch.setattr(context_module, '_utc_now', lambda: fixed_now)
    environment = {
        **_environment(tmp_path),
        'ATLANTICUS_JOB_SCHEDULE_CRON': '*/10 * * * *',
    }
    definition = JobDefinition(
        module_name='lifecycle_job',
        service_name='scheduled-drain-job',
        run_once=True,
        iteration_timeout_seconds=5,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=20,
        lease_timeout_seconds=30,
        lease_renew_seconds=5,
        lease_wait_seconds=0,
        resource_sample_seconds=0.01,
    )
    calls: list[str] = []

    def fail_drain(context: JobRuntimeContext) -> None:
        context.assert_lease_current()
        raise ValueError('drain failed')

    with pytest.raises(ValueError, match='drain failed'):
        execute_job(
            definition=definition,
            iteration=lambda context: calls.append('first'),
            drain=fail_drain,
            argv=[],
            environ=environment,
        )

    result = execute_job(
        definition=definition,
        iteration=lambda context: calls.append('retry'),
        argv=[],
        environ=environment,
    )

    authority = json.loads(
        (tmp_path / 'ada/.runtime/authority/scheduled-drain-job.json').read_text(encoding='utf-8')
    )
    assert result.status is OperationStatus.SUCCESS
    assert calls == ['first', 'retry']
    assert authority['generation'] == 2
    assert authority['last_completed_scheduled_at_utc'] == '2026-08-23T21:10:00+00:00'


def test_execute_job_rejects_non_callable_lifecycle_hooks(tmp_path) -> None:
    definition = _definition(service_name='invalid-hook-job')

    with pytest.raises(TypeError, match='recovery must be callable'):
        execute_job(
            definition=definition,
            iteration=lambda context: None,
            recovery=object(),
            argv=[],
            environ=_environment(tmp_path),
        )
    with pytest.raises(TypeError, match='drain must be callable'):
        execute_job(
            definition=definition,
            iteration=lambda context: None,
            drain=object(),
            argv=[],
            environ=_environment(tmp_path),
        )
