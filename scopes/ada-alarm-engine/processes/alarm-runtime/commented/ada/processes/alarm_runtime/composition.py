# Espejo pedagógico de la composición ejecutable del Alarm Runtime.
# Publica CURRENT y FACTS después de recovery y después de confirmar commits.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.alarms.persistence import LocalAlarmMaterializationStore, materialization_root
from ada.alarms.persistence.operational import AlarmPersistence
from ada.contracts.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada.processes.alarm_runtime.cycle import AlarmEvaluationCycle
from ada.processes.alarm_runtime.durable_adoption import AlarmDurableAdopter
from ada.processes.alarm_runtime.durable_commit import AlarmDurableCycleCommitter
from ada.processes.alarm_runtime.durable_recovery import (
    AlarmDurableRecovery,
    RecoveredAlarmAuthority,
)
from ada.processes.alarm_runtime.job import AlarmRuntimeIterationResult, AlarmRuntimeJob
from ada.processes.alarm_runtime.lifecycle import AlarmLifecycleCycle
from ada.processes.alarm_runtime.publication import (
    AlarmCommittedFactsExporter,
    AlarmDurableCurrentPublisher,
)
from ada.processes.alarm_runtime.publication.operational import AlarmDurablePublications
from ada.processes.alarm_runtime.session import AlarmEvaluatorRegistry
from ada.processes.alarm_runtime.settings import AlarmRuntimeSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.operational_data.datasets import RoutedDatasetSourceReader
from atlanticus.operational_data.sources import (
    DataInputLoader,
    DataSourceApplications,
    build_current_source_registry,
)
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)


@dataclass(slots=True)
class AlarmRuntimeComposition:
    configuration: ResolvedConfiguration
    runtime_configuration: RuntimeConfiguration
    settings: AlarmRuntimeSettings
    job: AlarmRuntimeJob
    publications: AlarmDurablePublications
    definition: JobDefinition

    def recover(self, context: JobRuntimeContext) -> RecoveredAlarmAuthority:
        # El Engine recupera y valida autoridad EFFECTIVE antes de publicar nada.
        authority = self.job.recover(context)
        # Se reintentan todas las publicaciones, aun si no hubo nuevos ciclos.
        self.publications.reconcile(context, force=True)
        return authority

    def run_iteration(self, context: JobRuntimeContext) -> AlarmRuntimeIterationResult:
        # En caso de fallo anterior, reconciliamos antes de un nuevo commit.
        self.publications.reconcile(context)
        result = self.job.run_iteration(context)
        # El commit durable ya terminó dentro de job.run_iteration.
        # Una excepción de publicación deja intacta la autoridad WAL.
        self.publications.reconcile(context)
        return result

    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            iteration=self.run_iteration,
            recovery=self.recover,
            argv=argv,
            environ=self.configuration.values,
        )


def build_composition(
    *,
    configuration: ResolvedConfiguration,
    evaluator_registry: AlarmEvaluatorRegistry,
) -> AlarmRuntimeComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be a ResolvedConfiguration')
    if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
        raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
    settings = AlarmRuntimeSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
    configuration_reader = LocalAlarmMaterializationStore(
        root=materialization_root(runtime_configuration.application_root),
    )
    registry = build_current_source_registry(pi_source=settings.pi_source)
    applications = DataSourceApplications(
        pi=settings.pi_application,
        dispatch=settings.dispatch_application,
        blockgrade=settings.blockgrade_application,
        remanentes=settings.remanentes_application,
        fabrica_planes=settings.fabrica_planes_application,
        fabrica_kpis=settings.fabrica_kpis_application,
        meteodata=settings.meteodata_application,
    )
    data_reader = RoutedDatasetSourceReader(
        volume_path=runtime_configuration.volume_path,
        applications=applications,
        registry=registry,
    )
    cycle = AlarmEvaluationCycle(loader=DataInputLoader(reader=data_reader, registry=registry))
    # Persistencia compartida: su WAL/snapshot nunca se modifica por el publicador.
    operational = AlarmPersistence(application_root=runtime_configuration.application_root)
    durable_recovery = AlarmDurableRecovery(
        persistence=operational,
        materializations=configuration_reader,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    # Salidas propias de Alarm Engine y separadas de runtime/state.
    output_root = runtime_configuration.application_root / 'alarms' / 'output'
    publications = AlarmDurablePublications(
        persistence=operational,
        facts=AlarmCommittedFactsExporter(
            root=output_root, source_key=ALARM_CONFIGURATION_SOURCE_KEY
        ),
        current=AlarmDurableCurrentPublisher(
            root=output_root, source_key=ALARM_CONFIGURATION_SOURCE_KEY
        ),
    )
    job = AlarmRuntimeJob(
        reader=configuration_reader,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        evaluator_registry=evaluator_registry,
        source_applications=applications,
        cycle=cycle,
        lifecycle=AlarmLifecycleCycle(),
        durable_recovery=durable_recovery,
        durable_committer=AlarmDurableCycleCommitter(persistence=operational),
        durable_adopter=AlarmDurableAdopter(
            persistence=operational,
            materializations=configuration_reader,
            source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        ),
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_runtime',
        service_name='alarm-runtime',
        job_key='alarm-runtime',
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
    return AlarmRuntimeComposition(
        configuration=configuration,
        runtime_configuration=runtime_configuration,
        settings=settings,
        job=job,
        publications=publications,
        definition=definition,
    )
