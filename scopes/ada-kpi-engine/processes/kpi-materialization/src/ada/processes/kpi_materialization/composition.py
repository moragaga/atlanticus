from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import MappingProxyType

from ada.kpis.materialization import LocalKpiRegistryStore, materialization_root
from ada.processes.kpi_materialization.job import KpiMaterializationJob
from ada.processes.kpi_materialization.repository import CosmosKpiRegistryRepository
from ada.processes.kpi_materialization.settings import KpiMaterializationSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)


@dataclass(slots=True)
class KpiMaterializationComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiMaterializationSettings
    job: KpiMaterializationJob
    definition: JobDefinition
    clients: Mapping[str, CosmosClient]

    def execute(
        self,
        *,
        argv: Sequence[str] | None = None,
    ) -> RuntimeExecutionResult:
        with ExitStack() as stack:
            for client in self.clients.values():
                stack.callback(client.close)
            return execute_job(
                definition=self.definition,
                iteration=self.job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
    connections: Mapping[str, CosmosSettings],
) -> KpiMaterializationComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    if not isinstance(connections, Mapping) or not connections:
        raise ValueError('connections must contain at least one tool')
    settings = KpiMaterializationSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    clients: dict[str, CosmosClient] = {}
    repositories: dict[str, CosmosKpiRegistryRepository] = {}
    for tool_key, cosmos_settings in sorted(connections.items()):
        client = CosmosClient(settings=cosmos_settings)
        clients[tool_key] = client
        repositories[tool_key] = CosmosKpiRegistryRepository(
            tool_key=tool_key,
            client=client,
        )
    job = KpiMaterializationJob(
        repositories=repositories,
        store=LocalKpiRegistryStore(
            root=materialization_root(runtime_configuration.volume_path),
        ),
    )
    definition = JobDefinition(
        module_name='ada.processes.kpi_materialization',
        service_name='kpi-materialization',
        job_key='kpi-materialization',
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
    return KpiMaterializationComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        job=job,
        definition=definition,
        clients=MappingProxyType(clients),
    )
