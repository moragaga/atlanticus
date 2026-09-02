import ada_command_center.processes.alarms_runtime as alarms_runtime
from ada_command_center.processes.alarms_runtime import (
    DEFAULT_ALARM_RUNTIME_ITERATION_PERIOD_SECONDS,
    AlarmCommitTimeProvider,
    AlarmConfigurationAdoptionExecutor,
    AlarmConfigurationRevision,
    AlarmConfigurationRevisionError,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    AlarmExecutionEntry,
    AlarmExecutionIteration,
    AlarmExecutionIterationError,
    AlarmExecutionSession,
    AlarmExecutionSessionError,
    AlarmGroupCycleResult,
    AlarmIterationData,
    AlarmIterationDataError,
    AlarmIterationLoader,
    AlarmIterationSourceLoader,
    AlarmOperationalCycle,
    AlarmOperationalCycleError,
    AlarmOperationalCycleResult,
    AlarmOperationalInputs,
    AlarmPendingDeactivationRequest,
    AlarmRuntimeComposition,
    AlarmRuntimeCompositionError,
    AlarmRuntimeGroup,
    AlarmRuntimeIterationExecutor,
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobComposition,
    AlarmRuntimeJobCompositionError,
    AlarmRuntimeJobIterationResult,
    ConfigurationAdoptionChange,
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionExecutionError,
    ConfigurationAdoptionExecutionResult,
    ConfigurationAdoptionGroupResult,
    ConfigurationAdoptionPlan,
    ConfigurationAdoptionPlanError,
    ConfigurationAdoptionRejectionReason,
    __version__,
    build_alarm_execution_session,
    build_alarm_runtime_composition,
    compose_engine_commit_record,
    decode_group_runtime_snapshot,
    encode_group_runtime_snapshot,
    execute_alarm_runtime_job,
    plan_configuration_adoption,
)


def test_public_api_and_version() -> None:
    exported = (
        AlarmCommitTimeProvider,
        AlarmConfigurationAdoptionExecutor,
        AlarmConfigurationRevision,
        AlarmConfigurationRevisionError,
        AlarmEvaluatorContract,
        AlarmEvaluatorRegistry,
        AlarmExecutionEntry,
        AlarmExecutionIteration,
        AlarmExecutionIterationError,
        AlarmExecutionSession,
        AlarmExecutionSessionError,
        AlarmGroupCycleResult,
        AlarmIterationData,
        AlarmIterationDataError,
        AlarmIterationLoader,
        AlarmIterationSourceLoader,
        AlarmOperationalCycle,
        AlarmOperationalCycleError,
        AlarmOperationalCycleResult,
        AlarmOperationalInputs,
        AlarmPendingDeactivationRequest,
        AlarmRuntimeComposition,
        AlarmRuntimeCompositionError,
        AlarmRuntimeGroup,
        AlarmRuntimeIterationExecutor,
        AlarmRuntimeJobAdoptionOutcome,
        AlarmRuntimeJobComposition,
        AlarmRuntimeJobCompositionError,
        AlarmRuntimeJobIterationResult,
        ConfigurationAdoptionChange,
        ConfigurationAdoptionDisposition,
        ConfigurationAdoptionExecutionError,
        ConfigurationAdoptionExecutionResult,
        ConfigurationAdoptionGroupResult,
        ConfigurationAdoptionPlan,
        ConfigurationAdoptionPlanError,
        ConfigurationAdoptionRejectionReason,
    )
    assert all(item is not None for item in exported)
    assert DEFAULT_ALARM_RUNTIME_ITERATION_PERIOD_SECONDS == 5.0
    assert callable(build_alarm_execution_session)
    assert callable(build_alarm_runtime_composition)
    assert callable(compose_engine_commit_record)
    assert callable(decode_group_runtime_snapshot)
    assert callable(encode_group_runtime_snapshot)
    assert callable(execute_alarm_runtime_job)
    assert callable(plan_configuration_adoption)
    assert __version__ == '1.0.0'


def test_deferred_public_api_is_absent() -> None:
    for name in (
        'AlarmDurableInputConsumer',
        'AlarmInputCursor',
        'AlarmInputLocator',
        'AlarmInputRecord',
        'AlarmInputSource',
        'AlarmInputStream',
        'FileRuntimeRevisionCache',
        'FileRuntimeRevisionSource',
        'RuntimeRevisionResolver',
        'RuntimeRevisionSource',
    ):
        assert not hasattr(alarms_runtime, name)
