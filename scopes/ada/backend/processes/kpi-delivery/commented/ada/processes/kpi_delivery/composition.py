# Espejo pedagógico del módulo productivo.
# Los comentarios explican la responsabilidad de la frontera sin alterar su semántica.
# Composition coordina infraestructura una vez al arranque y luego entrega un job funcional puro.
# El Registry se valida/lee y el contenedor de salida propio se asegura antes de execute_job.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.kpis.persistence import (
    KpiCommitStateRepository,
    KpiEvaluationRepository,
    KpiPersistencePaths,
)
from ada.processes.kpi_delivery.configuration import KpiDeliveryRegistryRepository
from ada.processes.kpi_delivery.job import KpiLatestDeliveryJob
from ada.processes.kpi_delivery.repository import KpiLatestSnapshotRepository
from ada.processes.kpi_delivery.settings import KpiDeliveryProcessSettings
from ada.processes.kpi_delivery.state import KpiLatestDeliveryCheckpointStore
from ada.processes.kpi_delivery.storage import (
    KPI_LATEST_DELIVERY_CONTAINER_SPEC,
    KPI_REGISTRY_CONTAINER_SPEC,
)
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import CosmosClient, CosmosProvisioner
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.state import AtomicStateStore


@dataclass(slots=True)
class KpiDeliveryComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiDeliveryProcessSettings
    registry_repository: KpiDeliveryRegistryRepository
    kpi_state: KpiCommitStateRepository
    evaluations: KpiEvaluationRepository
    checkpoint: KpiLatestDeliveryCheckpointStore
    snapshots: KpiLatestSnapshotRepository
    definition: JobDefinition
    cosmos_client: CosmosClient
    cosmos_provisioner: CosmosProvisioner

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with self.cosmos_client:
            self.cosmos_provisioner.validate_containers((KPI_REGISTRY_CONTAINER_SPEC,))
            self.cosmos_provisioner.ensure_containers((KPI_LATEST_DELIVERY_CONTAINER_SPEC,))
            frozen_configuration = self.registry_repository.read()
            job = KpiLatestDeliveryJob(
                configuration=frozen_configuration,
                kpi_state=self.kpi_state,
                evaluations=self.evaluations,
                checkpoint=self.checkpoint,
                snapshots=self.snapshots,
            )
            return execute_job(
                definition=self.definition,
                iteration=job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(*, configuration: ResolvedConfiguration) -> KpiDeliveryComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = KpiDeliveryProcessSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    upstream_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=settings.kpi_runtime_application,
    )
    own_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=runtime_configuration.application,
    )
    evaluations = KpiEvaluationRepository(
        paths=KpiPersistencePaths(upstream_store.application_root),
    )
    cosmos_client = CosmosClient(settings=settings.cosmos)
    cosmos_provisioner = CosmosProvisioner(client=cosmos_client)
    registry_repository = KpiDeliveryRegistryRepository(client=cosmos_client)
    snapshots = KpiLatestSnapshotRepository(
        client=cosmos_client,
        container_name=KPI_LATEST_DELIVERY_CONTAINER_SPEC.name,
    )
    definition = _job_definition(poll_interval_seconds=settings.poll_interval_seconds)
    return KpiDeliveryComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        registry_repository=registry_repository,
        kpi_state=KpiCommitStateRepository(upstream_store),
        evaluations=evaluations,
        checkpoint=KpiLatestDeliveryCheckpointStore(store=own_store),
        snapshots=snapshots,
        definition=definition,
        cosmos_client=cosmos_client,
        cosmos_provisioner=cosmos_provisioner,
    )


def _job_definition(*, poll_interval_seconds: float) -> JobDefinition:
    return JobDefinition(
        module_name='ada.processes.kpi_delivery',
        service_name='kpi-delivery',
        job_key='kpi-delivery',
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
