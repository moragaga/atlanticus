from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ada.contracts.alarms import AlarmIdentity
from ada_command_center.processes.alarms_runtime import (
    AlarmRuntimeProcessComposition,
    __version__,
    build_alarm_runtime_process,
)
from ada_command_center.processes.alarms_runtime.catalog import build_alarm_evaluator_registry
from ada_command_center.processes.alarms_runtime.settings import AlarmRuntimeSettings
from ada_command_center.processes.alarms_runtime.source_reader import (
    build_configured_alarm_source_adapter,
)
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.runtime import JobDefinition, RuntimeConfiguration


# El commit debe ser posterior o igual al instante lógico evaluado.
class _CommitTime:
    def committed_at(self, *, cycle_at: datetime) -> datetime:
        return max(datetime.now(UTC), cycle_at)


# Los IDs nuevos se generan con UUID; el estado durable conserva los anteriores.
def _occurrence_id(_identity: AlarmIdentity, _at: datetime) -> str:
    return f'occ-{uuid4().hex}'


# Los episodios usan un espacio de identificadores diferenciado.
def _episode_id(_priority_group: str, _at: datetime) -> str:
    return f'episode-{uuid4().hex}'


# Esta capa une componentes existentes: no contiene lógica de lifecycle ni persistencia.
def build_application(*, configuration: ResolvedConfiguration) -> AlarmRuntimeProcessComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be ResolvedConfiguration')
    settings = AlarmRuntimeSettings.from_configuration(configuration)
    runtime_configuration = RuntimeConfiguration.from_sources(environ=configuration.values)
# El adaptador construye el registry de fuentes y la lectura por APPLICATION.
    source_loader = build_configured_alarm_source_adapter(
        volume_path=runtime_configuration.volume_path,
        pi_source=settings.pi_source,
        pi_application=settings.pi_application,
        dispatch_application=settings.dispatch_application,
        blockgrade_application=settings.blockgrade_application,
        remanentes_application=settings.remanentes_application,
        fabrica_planes_application=settings.fabrica_planes_application,
    )
# Los límites del job son los mismos del proceso Materialization actual.
    definition = JobDefinition(
        module_name='ada_command_center.processes.alarms_runtime',
        service_name='alarms-runtime',
        job_key='alarms-runtime',
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
# La función existente conserva WAL, EFFECTIVE, recovery y fencing.
    return build_alarm_runtime_process(
        runtime_configuration=runtime_configuration,
        definition=definition,
        source_key=settings.source_key,
        evaluator_registry=build_alarm_evaluator_registry(),
        source_loader=source_loader,
        technical_evidence_contract=settings.technical_evidence_contract,
        occurrence_id_factory=_occurrence_id,
        episode_id_factory=_episode_id,
        commit_time_provider=_CommitTime(),
        runtime_artifact_version=__version__,
    )
