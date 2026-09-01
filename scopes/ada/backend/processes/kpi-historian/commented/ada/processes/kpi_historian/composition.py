# Composición explícita de repositorios, state, DatasetRuntime y Job Runtime.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.kpis.persistence import (
    KpiCommitStateRepository,
    KpiEvaluationRepository,
    KpiPersistencePaths,
)
from ada.processes.kpi_historian.history import KpiHistorianMaterializer
from ada.processes.kpi_historian.job import KpiHistorianJob
from ada.processes.kpi_historian.settings import KpiHistorianSettings
from ada.processes.kpi_historian.state import KpiHistorianAuthorityStore
from atlanticus.configuration import ResolvedConfiguration
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
class KpiHistorianComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiHistorianSettings
    kpi_state: KpiCommitStateRepository
    evaluations: KpiEvaluationRepository
    authority: KpiHistorianAuthorityStore
    history: KpiHistorianMaterializer
    job: KpiHistorianJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            iteration=self.job.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


def build_composition(*, configuration: ResolvedConfiguration) -> KpiHistorianComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    settings = KpiHistorianSettings.from_configuration(configuration)
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
    dataset_runtime = DatasetRuntime(
        store=ParquetDatasetStore(root=runtime_configuration.application_root / 'datasets')
    )
    kpi_state = KpiCommitStateRepository(upstream_store)
    authority = KpiHistorianAuthorityStore(store=own_store)
    history = KpiHistorianMaterializer(runtime=dataset_runtime)
    job = KpiHistorianJob(
        kpi_state=kpi_state,
        evaluations=evaluations,
        authority=authority,
        history=history,
    )
    definition = _job_definition(poll_interval_seconds=settings.poll_interval_seconds)
    return KpiHistorianComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        kpi_state=kpi_state,
        evaluations=evaluations,
        authority=authority,
        history=history,
        job=job,
        definition=definition,
    )


def _job_definition(*, poll_interval_seconds: float) -> JobDefinition:
    return JobDefinition(
        module_name='ada.processes.kpi_historian',
        service_name='kpi-historian',
        job_key='kpi-historian',
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
