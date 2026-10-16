# Construye el Job y aplica la política interna de presentación disponible actualmente.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ada.processes.alarm_modeler.presentation_policy import (
    CAROUSEL_ROTATION_SECONDS,
    CAROUSEL_VISIBLE_SLOTS,
)
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
class AlarmModelerComposition:
    configuration: ResolvedConfiguration
    settings: AlarmModelerSettings
    processor: AlarmModelerProcessor
    definition: JobDefinition

    # Recupera y comprueba el documento ya publicado.
    def recover(self, context: JobRuntimeContext) -> None:
        self.processor.recover(context)

    # Publica solo cuando el procesador detecta un cambio semántico.
    def run_iteration(self, context: JobRuntimeContext):
        result = self.processor.run_iteration(context)
        if result.status == 'PUBLISHED':
            context.set_iteration_fact('modeler_live_alarms', result.live_alarms)
            context.set_iteration_fact('modeler_attention_alarms', result.attention_alarms)
            context.set_iteration_fact('modeler_tools', result.tools)
            context.mark_iteration_work()
            context.request_iteration_summary()
        return result

    # Mantiene el ciclo, lease y fencing del runtime común.
    def execute(self, *, argv: Sequence[str] | None = None) -> RuntimeExecutionResult:
        return execute_job(
            definition=self.definition,
            recovery=self.recover,
            iteration=self.run_iteration,
            argv=argv,
            environ=self.configuration.values,
        )


# El intervalo de carousel ya no se lee de .env; queue-in-queue se integrará después.
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
        rotation_seconds=CAROUSEL_ROTATION_SECONDS,
        max_visible_slots=CAROUSEL_VISIBLE_SLOTS,
    )
    definition = JobDefinition(
        module_name='ada.processes.alarm_modeler',
        service_name='alarm-modeler',
        job_key='alarm-modeler',
        poll_interval_seconds=settings.poll_seconds,
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
