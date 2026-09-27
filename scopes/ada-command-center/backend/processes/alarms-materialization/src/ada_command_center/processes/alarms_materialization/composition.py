from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada_command_center.processes.alarms_materialization.acquisition import AlarmCandidateAcquirer
from ada_command_center.processes.alarms_materialization.job import AlarmMaterializationJob
from ada_command_center.processes.alarms_materialization.publication import (
    AlarmMaterializationPublisher,
    CosmosAlarmMaterializationResultStore,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    JsonFileAlarmQualificationProvider,
)
from ada_command_center.processes.alarms_materialization.settings import (
    AlarmMaterializationSettings,
)
from ada_command_center.web.alarms.projection.cosmos import (
    CosmosAlarmConfigurationProjectionStore,
    CosmosAlarmConfigurationProjectionStoreSettings,
)
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerSpec,
    CosmosProvisioner,
)
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.web.source.models import SourceKey


def compose_cosmos_alarm_candidate_acquirer(
    *, cosmos_client: CosmosClient, container_name: str, source_key: SourceKey
) -> AlarmCandidateAcquirer:
    return AlarmCandidateAcquirer(
        projection=CosmosAlarmConfigurationProjectionStore(
            client=cosmos_client,
            settings=CosmosAlarmConfigurationProjectionStoreSettings(container_name=container_name),
        ),
        source_key=source_key,
    )


@dataclass(slots=True)
class AlarmMaterializationComposition:
    configuration: ResolvedConfiguration
    settings: AlarmMaterializationSettings
    cosmos: CosmosClient
    job: AlarmMaterializationJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with self.cosmos:
            names = {self.settings.projection_container, self.settings.output_container}
            CosmosProvisioner(client=self.cosmos).validate_containers(
                tuple(
                    CosmosContainerSpec(name=name, partition_key_path='/partition_key')
                    for name in sorted(names)
                )
            )
            return execute_job(
                definition=self.definition,
                iteration=self.job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(*, configuration: ResolvedConfiguration) -> AlarmMaterializationComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = AlarmMaterializationSettings.from_configuration(configuration)
    RuntimeConfiguration.from_sources(environ=configuration.values)
    client = CosmosClient(settings=settings.cosmos)
    acquirer = compose_cosmos_alarm_candidate_acquirer(
        cosmos_client=client,
        container_name=settings.projection_container,
        source_key=SourceKey(settings.source_key),
    )
    job = AlarmMaterializationJob(
        acquirer=acquirer,
        qualifications=JsonFileAlarmQualificationProvider(settings.qualification_file),
        publisher=AlarmMaterializationPublisher(
            CosmosAlarmMaterializationResultStore(
                client=client, container_name=settings.output_container
            )
        ),
    )
    definition = JobDefinition(
        module_name='ada_command_center.processes.alarms_materialization',
        service_name='alarms-materialization',
        job_key='alarms-materialization',
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
        settings=settings,
        cosmos=client,
        job=job,
        definition=definition,
    )
