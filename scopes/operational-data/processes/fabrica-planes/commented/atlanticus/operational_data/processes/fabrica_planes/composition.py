# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass

from atlanticus.configuration import ResolvedConfiguration
from atlanticus.data_producers.fabrica import (
    FabricaDataProducerComponents,
    FabricaStreamDefinition,
    build_fabrica_data_producer,
)
from atlanticus.operational_data.processes.fabrica_planes.catalog import build_catalog
from atlanticus.operational_data.processes.fabrica_planes.settings import FabricaProcessSettings
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)

JOB_DEFINITION = JobDefinition(
    module_name='atlanticus.operational_data.processes.fabrica_planes',
    service_name='fabrica-planes',
    job_key='fabrica-planes-materialization',
    run_once=True, sleep_seconds=0,
    iteration_timeout_seconds=160, execution_timeout_seconds=180,
    shutdown_grace_seconds=10, lease_timeout_seconds=30,
    lease_renew_seconds=10, lease_wait_seconds=None,
    lease_poll_seconds=1, resource_sample_seconds=5,
)


@dataclass(slots=True)
# Contrato de FabricaProcessComposition.
class FabricaProcessComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: FabricaProcessSettings
    catalog: FabricaStreamDefinition
    producer: FabricaDataProducerComponents

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with ExitStack() as stack:
            for storage in self.producer.storages.values():
                stack.enter_context(storage)
            return execute_job(
                definition=JOB_DEFINITION,
                iteration=self.producer.job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


# Construye una ejecución independiente y su estado propio.
def build_composition(
    *, configuration: ResolvedConfiguration, catalog: FabricaStreamDefinition | None = None,
) -> FabricaProcessComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    resolved_catalog = build_catalog() if catalog is None else catalog
    if not isinstance(resolved_catalog, FabricaStreamDefinition) or resolved_catalog.stream_key != 'planes':
        raise ValueError('catalog must define only the planes stream')
    settings = FabricaProcessSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    producer = build_fabrica_data_producer(
        runtime_configuration=runtime_configuration,
        definitions=(resolved_catalog,),
        connections={'planes': settings.connection},
        idle_seconds=settings.idle_seconds,
        producer_key='fabrica-planes',
        dataset_namespace=('fabrica',),
    )
    return FabricaProcessComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        catalog=resolved_catalog,
        producer=producer,
    )
