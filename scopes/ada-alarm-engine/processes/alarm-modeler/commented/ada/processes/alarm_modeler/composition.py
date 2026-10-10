# Compone el Job con su almacén de salida, entradas de Runtime y cadencias independientes.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.processes.alarm_modeler.processor import AlarmModelerProcessor
from ada.processes.alarm_modeler.settings import AlarmModelerSettings
from atlanticus.configuration import ResolvedConfiguration
from atlanticus.runtime import (
    JobDefinition,
    JobRuntimeContext,
    RuntimeConfiguration,
    RuntimeExecutionResult,
    execute_job,
)
from atlanticus.runtime.storage import resolve_application_root


@dataclass(slots=True)
# Responsabilidad de AlarmModelerComposition: ejecutar el contrato local sin efectos implícitos.
class AlarmModelerComposition:
    configuration: ResolvedConfiguration
    settings: AlarmModelerSettings
    processor: AlarmModelerProcessor
    definition: JobDefinition

    # Comprueba el último documento publicado; no genera historial ni replay.
    def recover(self, context: JobRuntimeContext) -> None:
        self.processor.recover(context)

    # Comprueba fuentes, filtra cambios y publica solo bajo el fence del Job.
    def run_iteration(self, context: JobRuntimeContext):
        result = self.processor.run_iteration(context)
        if result.status == 'PUBLISHED':
            context.set_iteration_fact('modeler_live_alarms', result.live_alarms)
            context.set_iteration_fact('modeler_attention_alarms', result.attention_alarms)
            context.set_iteration_fact('modeler_tools', result.tools)
            context.mark_iteration_work()
            context.request_iteration_summary()
        return result

    # Utiliza el Runtime común de Atlanticus para leases, fence y ciclo de ejecución.
    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            recovery=self.recover,
            iteration=self.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


# Resuelve APPLICATION del productor y crea un proceso autónomo de sondeo corto.
def build_composition(*, configuration: ResolvedConfiguration) -> AlarmModelerComposition:
    if not isinstance(configuration, ResolvedConfiguration):
        raise TypeError('configuration must be ResolvedConfiguration')
    settings = AlarmModelerSettings.from_configuration(configuration)
    runtime = RuntimeConfiguration.from_sources(environ=configuration.values)
    producer_root = resolve_application_root(
        runtime.volume_path, application=settings.runtime_application
    )
    processor = AlarmModelerProcessor(
        runtime_root=producer_root,
        output_root=runtime.application_root / 'alarms' / 'modeler' / 'output',
        rotation_seconds=settings.rotation_seconds,
        max_visible_slots=settings.max_visible_slots,
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_modeler',
        service_name='alarm-modeler',
        job_key='alarm-modeler',
        sleep_seconds=settings.poll_seconds,
        iteration_timeout_seconds=580,
        execution_timeout_seconds=600,
        shutdown_grace_seconds=10,
        lease_timeout_seconds=30,
        lease_renew_seconds=10,
        lease_wait_seconds=None,
        lease_poll_seconds=1,
        resource_sample_seconds=5,
        iteration_summary_every=0,
    )
    return AlarmModelerComposition(
        configuration=configuration,
        settings=settings,
        processor=processor,
        definition=definition,
    )
