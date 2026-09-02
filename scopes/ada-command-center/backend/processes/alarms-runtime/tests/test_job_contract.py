from ada_command_center.processes.alarms_runtime import (
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobIterationResult,
)


def test_durable_adoption_without_cycle_requests_immediate_next_iteration() -> None:
    result = AlarmRuntimeJobIterationResult(
        adoption_outcome=AlarmRuntimeJobAdoptionOutcome.ADOPTED,
        cycle_executed=False,
    )
    assert result.immediate_next_iteration is True


def test_adoption_with_cycle_does_not_request_second_cycle_inside_iteration() -> None:
    result = AlarmRuntimeJobIterationResult(
        adoption_outcome=AlarmRuntimeJobAdoptionOutcome.ADOPTED,
        cycle_executed=True,
    )
    assert result.immediate_next_iteration is False


def test_non_adoption_does_not_request_immediate_next_iteration() -> None:
    result = AlarmRuntimeJobIterationResult(
        adoption_outcome=AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED,
        cycle_executed=True,
    )
    assert result.immediate_next_iteration is False
