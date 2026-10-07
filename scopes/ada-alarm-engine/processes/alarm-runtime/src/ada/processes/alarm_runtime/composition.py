from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.contracts.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada.processes.alarm_runtime.job import AlarmRuntimeJob
from ada.processes.alarm_runtime.session import AlarmEvaluatorRegistry
from ada.processes.alarm_runtime.settings import AlarmRuntimeSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)


@dataclass(slots=True)
class AlarmRuntimeComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: AlarmRuntimeSettings
    job: AlarmRuntimeJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            iteration=self.job.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
    evaluator_registry: AlarmEvaluatorRegistry,
) -> AlarmRuntimeComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
        raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
    settings = AlarmRuntimeSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    reader = LocalAlarmMaterializationStore(
        root=materialization_root(runtime_configuration.volume_path),
    )
    job = AlarmRuntimeJob(
        reader=reader,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        evaluator_registry=evaluator_registry,
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_runtime',
        service_name='alarm-runtime',
        job_key='alarm-runtime',
        sleep_seconds=settings.poll_interval_seconds,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
    return AlarmRuntimeComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        job=job,
        definition=definition,
    )
