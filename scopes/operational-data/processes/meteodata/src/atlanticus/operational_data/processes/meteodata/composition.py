from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from atlanticus.configuration import ResolvedConfiguration
from atlanticus.connectivity.http import HttpClient
from atlanticus.data_producers.meteodata import (
    MeteodataAcquirer,
    MeteodataJob,
    MeteodataMaterializer,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from atlanticus.operational_data.processes.meteodata.settings import MeteodataSettings
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)

METEODATA_JOB_DEFINITION = JobDefinition(
    module_name='atlanticus.operational_data.processes.meteodata',
    service_name='meteodata',
    job_key='meteodata-materialization',
    run_once=True,
    sleep_seconds=0,
    iteration_timeout_seconds=250,
    execution_timeout_seconds=275,
    shutdown_grace_seconds=10,
    lease_timeout_seconds=30,
    lease_renew_seconds=10,
    lease_wait_seconds=None,
    lease_poll_seconds=1,
    resource_sample_seconds=5,
)


@dataclass(slots=True)
class MeteodataComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: MeteodataSettings
    client: HttpClient
    definition: JobDefinition
    job: MeteodataJob
    dataset_runtime: DatasetRuntime

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        with self.client:
            return execute_job(
                definition=self.definition,
                iteration=self.job.run_iteration,
                argv=argv,
                environ=self.configuration.values,
            )


def build_composition(*, configuration: ResolvedConfiguration) -> MeteodataComposition:
    settings = MeteodataSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    client = HttpClient(settings=settings.http)
    dataset_runtime = DatasetRuntime(
        store=ParquetDatasetStore(root=runtime_configuration.application_root / 'datasets')
    )
    job = MeteodataJob(
        acquirer=MeteodataAcquirer(client=client),
        materializer=MeteodataMaterializer(runtime=dataset_runtime),
        lookback_minutes=settings.lookback_minutes,
        retry_delay_seconds=settings.retry_delay_seconds,
    )
    return MeteodataComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        client=client,
        definition=METEODATA_JOB_DEFINITION,
        job=job,
        dataset_runtime=dataset_runtime,
    )
