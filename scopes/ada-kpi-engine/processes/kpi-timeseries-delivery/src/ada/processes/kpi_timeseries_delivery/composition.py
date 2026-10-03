from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import MappingProxyType

from ada.kpis.materialization import LocalKpiRegistryStore, materialization_root
from ada.processes.kpi_timeseries_delivery.job import KpiTimeseriesDeliveryRuntimeJob
from ada.processes.kpi_timeseries_delivery.parallel import ParallelKpiTimeseriesPublisher
from ada.processes.kpi_timeseries_delivery.repository import KpiTimeseriesSnapshotRepository
from ada.processes.kpi_timeseries_delivery.rolling import KpiTimeseriesRollingRepository
from ada.processes.kpi_timeseries_delivery.settings import KpiTimeseriesDeliveryProcessSettings
from ada.processes.kpi_timeseries_delivery.state import (
    KpiHistorianAuthorityReader,
    KpiTimeseriesDeliveryCheckpointStore,
)
from ada.processes.kpi_timeseries_delivery.storage import (
    KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC,
)
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosProvisioner,
    CosmosSettings,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.state import AtomicStateStore


@dataclass(slots=True)
class KpiTimeseriesDeliveryComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiTimeseriesDeliveryProcessSettings
    job: KpiTimeseriesDeliveryRuntimeJob
    publishers: Mapping[str, KpiTimeseriesSnapshotRepository]
    parallel_publisher: ParallelKpiTimeseriesPublisher
    definition: JobDefinition
    clients: Mapping[str, CosmosClient]

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with ExitStack() as stack:
            for client in self.clients.values():
                stack.callback(client.close)
            stack.callback(self.parallel_publisher.close)
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
) -> KpiTimeseriesDeliveryComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    if not isinstance(connections, Mapping) or not connections:
        raise ValueError('connections must contain at least one tool')

    settings = KpiTimeseriesDeliveryProcessSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    historian_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=settings.historian_application,
    )
    own_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=runtime_configuration.application,
    )

    clients: dict[str, CosmosClient] = {}
    publishers: dict[str, KpiTimeseriesSnapshotRepository] = {}
    for tool_key, cosmos_settings in sorted(connections.items()):
        client = CosmosClient(settings=cosmos_settings)
        clients[tool_key] = client
        publishers[tool_key] = KpiTimeseriesSnapshotRepository(
            client=client,
            provisioner=CosmosProvisioner(client=client),
            container_spec=KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC,
        )
    frozen_publishers = MappingProxyType(publishers)
    parallel_publisher = ParallelKpiTimeseriesPublisher(
        publishers=frozen_publishers,
        max_workers=settings.max_workers,
    )

    job = KpiTimeseriesDeliveryRuntimeJob(
        store=LocalKpiRegistryStore(
            root=materialization_root(runtime_configuration.volume_path),
        ),
        expected_tool_keys=connections,
        historian=KpiHistorianAuthorityReader(store=historian_store),
        rolling=KpiTimeseriesRollingRepository(
            store=ParquetDatasetStore(root=historian_store.application_root),
        ),
        checkpoints=KpiTimeseriesDeliveryCheckpointStore(store=own_store),
        publisher=parallel_publisher,
    )
    return KpiTimeseriesDeliveryComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        job=job,
        publishers=frozen_publishers,
        parallel_publisher=parallel_publisher,
        definition=_job_definition(poll_interval_seconds=settings.poll_interval_seconds),
        clients=MappingProxyType(clients),
    )


def _job_definition(*, poll_interval_seconds: float) -> JobDefinition:
    return JobDefinition(
        module_name='ada.processes.kpi_timeseries_delivery',
        service_name='kpi-timeseries-delivery',
        job_key='kpi-timeseries-delivery',
        sleep_seconds=poll_interval_seconds,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
