from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    execute_job,
)


def _configuration(tmp_path) -> RuntimeConfiguration:
    return RuntimeConfiguration.from_sources(
        environ={
            'ENVIRONMENT': 'local',
            'APPLICATION': 'ada',
            'VOLUMEN_PATH': str(tmp_path),
        }
    )


def _environment(tmp_path) -> dict[str, str]:
    return {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada',
        'VOLUMEN_PATH': str(tmp_path),
    }


def _definition() -> JobDefinition:
    return JobDefinition(
        module_name='finite_job',
        service_name='finite-job',
        sleep_seconds=0,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=0,
        lease_poll_seconds=1,
        resource_sample_seconds=0.01,
    )


def test_completion_is_not_a_cancellation(tmp_path) -> None:
    context = JobRuntimeContext.create(
        definition=_definition(),
        configuration=_configuration(tmp_path),
        run_id='11111111-1111-1111-1111-111111111111',
        correlation_id='22222222-2222-2222-2222-222222222222',
    )

    context.complete_execution()

    assert context.execution_completed is True
    assert context.should_stop is False
    context.raise_if_cancelled()


def test_completion_wins_before_next_iteration_admission(tmp_path) -> None:
    iterations: list[int] = []

    def iteration(context: JobRuntimeContext) -> None:
        iterations.append(context.iteration)
        context.mark_iteration_work()
        context.set_next_iteration_delay(context.safe_remaining_seconds)
        context.complete_execution()

    result = execute_job(
        definition=_definition(),
        iteration=iteration,
        argv=[],
        environ=_environment(tmp_path),
    )

    assert iterations == [1]
    assert result.status.value == 'success'
    assert result.iteration_count == 1
    assert result.stop_reason == 'completed'
