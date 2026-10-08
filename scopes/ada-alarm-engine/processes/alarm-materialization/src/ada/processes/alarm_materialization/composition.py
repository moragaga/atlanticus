from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass

from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.processes.alarm_materialization.job import AlarmMaterializationJob
from ada.processes.alarm_materialization.repository import (
    CosmosAlarmConfigurationRepository,
)
from ada.processes.alarm_materialization.settings import AlarmMaterializationSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)


@dataclass(slots=True)
class AlarmMaterializationComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: AlarmMaterializationSettings
    cosmos: CosmosClient
    job: AlarmMaterializationJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with ExitStack() as stack:
            stack.callback(self.cosmos.close)
            return execute_job(
                definition=self.definition,
                iteration=self.job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
) -> AlarmMaterializationComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = AlarmMaterializationSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    cosmos = CosmosClient(settings=settings.cosmos)
    reader = CosmosAlarmConfigurationRepository(
        client=cosmos,
    )
    job = AlarmMaterializationJob(
        reader=reader,
        store=LocalAlarmMaterializationStore(
            root=materialization_root(runtime_configuration.application_root),
        ),
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_materialization',
        service_name='alarm-materialization',
        job_key='alarm-materialization',
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
    return AlarmMaterializationComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        cosmos=cosmos,
        job=job,
        definition=definition,
    )
