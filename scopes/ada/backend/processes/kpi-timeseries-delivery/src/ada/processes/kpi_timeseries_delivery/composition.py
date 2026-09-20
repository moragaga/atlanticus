from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.processes.kpi_timeseries_delivery.configuration import (
    KpiTimeseriesRegistryRepository,
)
from ada.processes.kpi_timeseries_delivery.history import KpiTimeseriesHistoryRepository
from ada.processes.kpi_timeseries_delivery.job import KpiTimeseriesDeliveryJob
from ada.processes.kpi_timeseries_delivery.repository import (
    KpiTimeseriesSnapshotRepository,
)
from ada.processes.kpi_timeseries_delivery.settings import (
    KpiTimeseriesDeliveryProcessSettings,
)
from ada.processes.kpi_timeseries_delivery.state import (
    KpiHistorianAuthorityReader,
    KpiTimeseriesDeliveryCheckpointStore,
)
from ada.processes.kpi_timeseries_delivery.storage import (
    KPI_REGISTRY_CONTAINER_SPEC,
    KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC,
)
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosClient, CosmosProvisioner
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
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
    registry_repository: KpiTimeseriesRegistryRepository
    historian: KpiHistorianAuthorityReader
    history: KpiTimeseriesHistoryRepository
    checkpoint: KpiTimeseriesDeliveryCheckpointStore
    snapshots: KpiTimeseriesSnapshotRepository
    definition: JobDefinition
    cosmos_client: CosmosClient
    cosmos_provisioner: CosmosProvisioner

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with self.cosmos_client:
            self.cosmos_provisioner.validate_containers((KPI_REGISTRY_CONTAINER_SPEC,))
            self.cosmos_provisioner.ensure_containers((KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC,))
            frozen_configuration = self.registry_repository.read()
            job = KpiTimeseriesDeliveryJob(
                configuration=frozen_configuration,
                historian=self.historian,
                history=self.history,
                checkpoint=self.checkpoint,
                snapshots=self.snapshots,
            )
            return execute_job(
                definition=self.definition,
                iteration=job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
) -> KpiTimeseriesDeliveryComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
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
    history_runtime = DatasetRuntime(
        store=ParquetDatasetStore(root=historian_store.application_root / 'datasets')
    )
    cosmos_client = CosmosClient(settings=settings.cosmos)
    cosmos_provisioner = CosmosProvisioner(client=cosmos_client)
    definition = _job_definition(poll_interval_seconds=settings.poll_interval_seconds)
    return KpiTimeseriesDeliveryComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        registry_repository=KpiTimeseriesRegistryRepository(client=cosmos_client),
        historian=KpiHistorianAuthorityReader(store=historian_store),
        history=KpiTimeseriesHistoryRepository(runtime=history_runtime),
        checkpoint=KpiTimeseriesDeliveryCheckpointStore(store=own_store),
        snapshots=KpiTimeseriesSnapshotRepository(
            client=cosmos_client,
            container_name=KPI_TIMESERIES_DELIVERY_CONTAINER_SPEC.name,
        ),
        definition=definition,
        cosmos_client=cosmos_client,
        cosmos_provisioner=cosmos_provisioner,
    )


def _job_definition(*, poll_interval_seconds: float) -> JobDefinition:
    return JobDefinition(
        module_name='ada.processes.kpi_timeseries_delivery',
        service_name='kpi-timeseries-delivery',
        job_key='kpi-timeseries-delivery',
        sleep_seconds=poll_interval_seconds,
        iteration_timeout_seconds=240,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
