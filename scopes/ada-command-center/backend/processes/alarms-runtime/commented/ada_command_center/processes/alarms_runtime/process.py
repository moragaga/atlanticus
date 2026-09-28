from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from ada_command_center.alarms.core import (
    EpisodeIdFactory,
    EvidenceContractRef,
    OccurrenceIdFactory,
)
from ada_command_center.processes.alarms_runtime.adoption_execution import (
    AlarmConfigurationAdoptionExecutor,
)
from ada_command_center.processes.alarms_runtime.composition import (
    build_alarm_runtime_composition,
)
from ada_command_center.processes.alarms_runtime.configured_iteration import (
    AlarmConfiguredIterationExecutor,
)
from ada_command_center.processes.alarms_runtime.cycle import (
    AlarmCommitTimeProvider,
    AlarmOperationalCycle,
)
from ada_command_center.processes.alarms_runtime.inputs import AlarmOperationalInputs
from ada_command_center.processes.alarms_runtime.iteration import AlarmIterationSourceLoader
from ada_command_center.processes.alarms_runtime.job_composition import (
    AlarmRuntimeJobComposition,
    execute_alarm_runtime_job,
)
from ada_command_center.processes.alarms_runtime.local_configuration import (
    RuntimeLocalConfigurationReader,
)
from ada_command_center.processes.alarms_runtime.operational_runner import (
    AlarmOperationalCycleRunner,
)
from ada_command_center.processes.alarms_runtime.session import AlarmEvaluatorRegistry
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
)

_RUNTIME_MODULE = 'ada_command_center.processes.alarms_runtime'
_RUNTIME_SERVICE = 'alarms-runtime'


# El reloj se inyecta para reproducir las fronteras temporales en pruebas.
def _now() -> datetime:
    return datetime.now(UTC)


# El host conserva la definición y la composición; no instancia servicios remotos.
@dataclass(slots=True)
class AlarmRuntimeProcessComposition:
    configuration: RuntimeConfiguration
    definition: JobDefinition
    job: AlarmRuntimeJobComposition
    operational_runner: AlarmOperationalCycleRunner

    def execute(
        self,
        *,
        argv: Sequence[str] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> RuntimeExecutionResult:
        values = os.environ if environ is None else environ
        if RuntimeConfiguration.from_sources(environ=values) != self.configuration:
            raise ValueError('execution environment does not match runtime composition')
        return execute_alarm_runtime_job(
            definition=self.definition,
            composition=self.job,
            argv=argv,
            environ=environ,
        )


# Se requieren explícitamente evaluadores, fuentes, evidencia y política del job.
def build_alarm_runtime_process(
    *,
    runtime_configuration: RuntimeConfiguration,
    definition: JobDefinition,
    source_key: str,
    evaluator_registry: AlarmEvaluatorRegistry,
    source_loader: AlarmIterationSourceLoader,
    technical_evidence_contract: EvidenceContractRef,
    occurrence_id_factory: OccurrenceIdFactory,
    episode_id_factory: EpisodeIdFactory,
    commit_time_provider: AlarmCommitTimeProvider,
    runtime_artifact_version: str,
    clock: Callable[[], datetime] = _now,
    operational_inputs_provider: Callable[[JobRuntimeContext], AlarmOperationalInputs] | None = None,
) -> AlarmRuntimeProcessComposition:
    if not isinstance(runtime_configuration, RuntimeConfiguration):
        raise TypeError('runtime_configuration must be RuntimeConfiguration')
    if not isinstance(definition, JobDefinition):
        raise TypeError('definition must be JobDefinition')
    if definition.module_name != _RUNTIME_MODULE or definition.service_name != _RUNTIME_SERVICE:
        raise ValueError('definition must identify the alarms-runtime service')
    if not isinstance(source_key, str) or not source_key or source_key != source_key.strip():
        raise ValueError('source_key must be non-empty text without surrounding whitespace')
    if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
        raise TypeError('evaluator_registry must be AlarmEvaluatorRegistry')
    if not isinstance(source_loader, AlarmIterationSourceLoader):
        raise TypeError('source_loader must implement AlarmIterationSourceLoader')
    if not isinstance(technical_evidence_contract, EvidenceContractRef):
        raise TypeError('technical_evidence_contract must be EvidenceContractRef')
    if (
        not isinstance(runtime_artifact_version, str)
        or not runtime_artifact_version
        or runtime_artifact_version != runtime_artifact_version.strip()
    ):
        raise ValueError('runtime_artifact_version must be non-empty text without padding')
    if not callable(occurrence_id_factory) or not callable(episode_id_factory):
        raise TypeError('occurrence_id_factory and episode_id_factory must be callable')
    if not isinstance(commit_time_provider, AlarmCommitTimeProvider):
        raise TypeError('commit_time_provider must implement AlarmCommitTimeProvider')
    if not callable(clock):
        raise TypeError('clock must be callable')
    if operational_inputs_provider is not None and not callable(operational_inputs_provider):
        raise TypeError('operational_inputs_provider must be callable or None')

    # La misma composición local gobierna recovery, adopción y commits del Engine.
    composition = build_alarm_runtime_composition(runtime_configuration=runtime_configuration)
    runner_options = (
        {} if operational_inputs_provider is None
        else {'operational_inputs_provider': operational_inputs_provider}
    )
    # El runner fija una única sesión y evita commits coincidentes por segundo UTC.
    runner = AlarmOperationalCycleRunner(
        composition=composition,
        source_loader=source_loader,
        cycle_factory=lambda session: AlarmOperationalCycle(
            session=session,
            composition=composition,
            occurrence_id_factory=occurrence_id_factory,
            episode_id_factory=episode_id_factory,
            commit_time_provider=commit_time_provider,
            runtime_artifact_version=runtime_artifact_version,
            technical_evidence_contract=technical_evidence_contract,
        ),
        clock=clock,
        **runner_options,
    )
    # READY es candidato; el ejecutor fija la revisión EFFECTIVE para todo el job.
    executor = AlarmConfiguredIterationExecutor(
        reader=RuntimeLocalConfigurationReader(
            volume_path=runtime_configuration.volume_path,
            source_key=source_key,
        ),
        evaluator_registry=evaluator_registry,
        adoption_executor=AlarmConfigurationAdoptionExecutor(
            composition=composition,
            commit_time_provider=commit_time_provider,
            runtime_artifact_version=runtime_artifact_version,
        ),
        run_cycle=runner,
        clock=clock,
    )
    return AlarmRuntimeProcessComposition(
        configuration=runtime_configuration,
        definition=definition,
        job=AlarmRuntimeJobComposition(composition=composition, iteration_executor=executor),
        operational_runner=runner,
    )
