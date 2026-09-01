from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.kpis.core import KpiCatalog
from ada.kpis.persistence import KpiPersistence
from ada.processes.kpi_runtime.catalog import build_catalog
from ada.processes.kpi_runtime.job import KpiRuntimeJob
from ada.processes.kpi_runtime.reader import RoutedDatasetSourceReader
from ada.processes.kpi_runtime.settings import KpiRuntimeSettings
from ada.processes.kpi_runtime.source_state import PiOperationalWatermarkReader
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.operational_data.planner import DataRequirementPlanner
from atlanticus.operational_data.sources import (
    DataSourceApplications,
    DataSourceLoader,
    build_current_source_registry,
)
from atlanticus.runtime import (
    JobDefinition,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.state import AtomicStateStore


@dataclass(slots=True)
class KpiRuntimeComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: KpiRuntimeSettings
    catalog: KpiCatalog
    job: KpiRuntimeJob
    definition: JobDefinition

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            iteration=self.job.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
    catalog: KpiCatalog | None = None,
) -> KpiRuntimeComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    resolved_catalog = build_catalog() if catalog is None else catalog
    if not isinstance(resolved_catalog, KpiCatalog):
        raise TypeError('catalog must be a KpiCatalog')
    settings = KpiRuntimeSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    registry = build_current_source_registry(pi_source=settings.pi_source)
    plan = DataRequirementPlanner().plan({spec.key: spec.requirements for spec in resolved_catalog})
    applications = DataSourceApplications(
        pi=settings.pi_application,
        dispatch=settings.dispatch_application,
        blockgrade=settings.blockgrade_application,
        remanentes=settings.remanentes_application,
        fabrica=settings.fabrica_application,
    )
    applications.validate_sources(plan.sources)
    reader = RoutedDatasetSourceReader(
        volume_path=runtime_configuration.volume_path,
        applications=applications,
        registry=registry,
        sources=plan.sources,
    )
    loader = DataSourceLoader(reader=reader, registry=registry)
    persistence = KpiPersistence.from_runtime(
        volume_path=runtime_configuration.volume_path,
        application=runtime_configuration.application,
    )
    source_store = AtomicStateStore(
        volume_path=runtime_configuration.volume_path,
        application=settings.pi_application,
    )
    source_watermarks = PiOperationalWatermarkReader(
        store=source_store,
        provider=settings.pi_source,
    )
    job = KpiRuntimeJob(
        catalog=resolved_catalog,
        plan=plan,
        loader=loader,
        persistence=persistence,
        source_watermarks=source_watermarks,
    )
    definition = JobDefinition(
        module_name='ada.processes.kpi_runtime',
        service_name='kpi-runtime',
        job_key='kpi-runtime',
        sleep_seconds=settings.poll_interval_seconds,
        iteration_timeout_seconds=240,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
    )
    return KpiRuntimeComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        catalog=resolved_catalog,
        job=job,
        definition=definition,
    )
