from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.processes.alarm_materialization.job import AlarmMaterializationJob
from ada.processes.alarm_materialization.repository import CosmosAlarmConfigurationRepository
from ada.processes.alarm_materialization.settings import AlarmMaterializationSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
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
        return execute_job(
            definition=self.definition,
            iteration=self.job.run_iteration,
            resource_scope=self._resource_scope,
            argv=argv,
            environ=self.configuration.values,
        )

    @contextmanager
    def _resource_scope(self, context: JobRuntimeContext) -> Iterator[None]:
        context.assert_lease_current()
        try:
            yield
        finally:
            self.cosmos.close()


def build_composition(
    *,
    configuration: ResolvedConfiguration,
) -> AlarmMaterializationComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = AlarmMaterializationSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    cosmos = CosmosClient(settings=settings.cosmos)
    reader = CosmosAlarmConfigurationRepository(client=cosmos)
    job = AlarmMaterializationJob(
        reader=reader,
        store=LocalAlarmMaterializationStore(
            root=materialization_root(runtime_configuration.application_root),
        ),
        readiness_retry_seconds=settings.poll_interval_seconds,
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_materialization',
        service_name='alarm-materialization',
        job_key='alarm-materialization',
        run_once=True,
        poll_interval_seconds=0,
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
