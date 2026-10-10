# Espejo pedagógico del código productivo: mismos contratos y ejecución.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.processes.alarm_historian.checkpoint import AlarmHistorianCheckpointStore
from ada.processes.alarm_historian.job import AlarmHistorianJob
from ada.processes.alarm_historian.reader import AlarmHistorianReader
from ada.processes.alarm_historian.settings import AlarmHistorianSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.runtime.storage import resolve_application_root


# Guarda la composición lista para ejecutar, sin recursos globales.
@dataclass(slots=True)
class AlarmHistorianComposition:
    configuration: ResolvedConfiguration
    settings: AlarmHistorianSettings
    job: AlarmHistorianJob
    definition: JobDefinition

    # Entrega la función iteración al ejecutor oficial de Atlanticus.
    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            iteration=self.job.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


# Separa fuente FACTS del productor y destino persistente del historiador.
def build_composition(*, configuration: ResolvedConfiguration) -> AlarmHistorianComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = AlarmHistorianSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    producer_root = resolve_application_root(
        runtime_configuration.volume_path, application=settings.producer_application
    )
    # El lector no accede al WAL: consume la publicación FACTS del productor.
    facts_root = producer_root / 'alarms' / 'output'
    # El contrato DatasetDefinition añade history/ o evidence/ según el dominio.
    history_root = runtime_configuration.application_root / 'alarms'
    # El checkpoint no comparte ubicación con los archivos Parquet.
    checkpoint = AlarmHistorianCheckpointStore(
        root=history_root / 'historian',
        stream_id=settings.stream_id,
        producer_application=settings.producer_application,
    )
    reader = AlarmHistorianReader(
        facts_root=facts_root, stream_id=settings.stream_id, max_records=settings.max_records
    )
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=history_root))
    job = AlarmHistorianJob(reader=reader, checkpoint=checkpoint, runtime=runtime)
    # Cada invocación procesa un lote, bajo su lease independiente.
    definition = JobDefinition(
        module_name='ada.processes.alarm_historian',
        service_name='alarm-historian',
        job_key='alarm-historian',
        run_once=True,
        sleep_seconds=0,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
    return AlarmHistorianComposition(
        configuration=configuration, settings=settings, job=job, definition=definition
    )
