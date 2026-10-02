# Espejo pedagógico de KPI Latest Delivery paralelo por Tool: composition.py.
from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import MappingProxyType

from ada.kpis.materialization import LocalKpiRegistryStore, materialization_root
from ada.kpis.persistence import (
    KpiCommitStateRepository,
    KpiEvaluationRepository,
    KpiPersistencePaths,
)
from ada.processes.kpi_delivery.configuration import (
    FrozenKpiDeliveryConfiguration,
    load_frozen_delivery_configurations,
)
from ada.processes.kpi_delivery.job import KpiLatestDeliveryJob
from ada.processes.kpi_delivery.parallel import ParallelKpiLatestPublisher
from ada.processes.kpi_delivery.repository import KpiLatestSnapshotRepository
from ada.processes.kpi_delivery.settings import KpiDeliveryProcessSettings
from ada.processes.kpi_delivery.state import KpiLatestDeliveryCheckpointStore
from ada.processes.kpi_delivery.storage import KPI_LATEST_DELIVERY_CONTAINER_SPEC
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosProvisioner,
    CosmosSettings,
)
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.state import AtomicStateStore


@dataclass(slots=True)
# Define una responsabilidad con estado o contrato propio.
class KpiDeliveryComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiDeliveryProcessSettings
    frozen_configurations: Mapping[str, FrozenKpiDeliveryConfiguration]
    kpi_state: KpiCommitStateRepository
    evaluations: KpiEvaluationRepository
    checkpoints: KpiLatestDeliveryCheckpointStore
    publishers: Mapping[str, KpiLatestSnapshotRepository]
    parallel_publisher: ParallelKpiLatestPublisher
    definition: JobDefinition
    clients: Mapping[str, CosmosClient]

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with ExitStack() as stack:
            for client in self.clients.values():
                stack.callback(client.close)
            stack.callback(self.parallel_publisher.close)
            job = KpiLatestDeliveryJob(
                configurations=self.frozen_configurations,
                kpi_state=self.kpi_state,
                evaluations=self.evaluations,
                checkpoints=self.checkpoints,
                publisher=self.parallel_publisher,
            )
            return execute_job(
                definition=self.definition,
                iteration=job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


# Expone una operación manteniendo validación explícita.
def build_composition(
    *,
    configuration: ResolvedConfiguration,
    connections: Mapping[str, CosmosSettings],
) -> KpiDeliveryComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    if not isinstance(connections, Mapping) or not connections:
        raise ValueError('connections must contain at least one tool')

    settings = KpiDeliveryProcessSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(
        environ=configuration.values
    )
    upstream_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=settings.kpi_runtime_application,
    )
    own_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=runtime_configuration.application,
    )
    local_registries = LocalKpiRegistryStore(
        root=materialization_root(runtime_configuration.volume_path)
    )
    frozen = load_frozen_delivery_configurations(
        store=local_registries,
        expected_tool_keys=connections,
    )
    clients: dict[str, CosmosClient] = {}
    publishers: dict[str, KpiLatestSnapshotRepository] = {}
    for tool_key, cosmos_settings in sorted(connections.items()):
        client = CosmosClient(settings=cosmos_settings)
        clients[tool_key] = client
        publishers[tool_key] = KpiLatestSnapshotRepository(
            client=client,
            provisioner=CosmosProvisioner(client=client),
            container_spec=KPI_LATEST_DELIVERY_CONTAINER_SPEC,
        )
    frozen_publishers = MappingProxyType(publishers)
    return KpiDeliveryComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        frozen_configurations=frozen,
        kpi_state=KpiCommitStateRepository(upstream_store),
        evaluations=KpiEvaluationRepository(
            paths=KpiPersistencePaths(upstream_store.application_root),
        ),
        checkpoints=KpiLatestDeliveryCheckpointStore(store=own_store),
        publishers=frozen_publishers,
        parallel_publisher=ParallelKpiLatestPublisher(
            publishers=frozen_publishers,
            max_workers=settings.max_workers,
        ),
        definition=_job_definition(
            poll_interval_seconds=settings.poll_interval_seconds,
        ),
        clients=MappingProxyType(clients),
    )


# Expone una operación manteniendo validación explícita.
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
