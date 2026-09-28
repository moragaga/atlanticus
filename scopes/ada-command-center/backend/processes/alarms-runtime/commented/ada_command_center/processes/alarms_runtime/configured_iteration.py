# Selección exacta de EFFECTIVE y consulta READY una vez antes del primer ciclo del job.
# El bootstrap se confirma mediante el WAL existente; no se inventa una revisión de origen.
# La sesión confirmada se inmoviliza en memoria de la ejecución; los ciclos siguientes sólo usan esa sesión.
# El ciclo operacional se inyecta porque su fuente de datos es una frontera independiente.
# Ante ausencia, READY inválida o READY aún no ejecutable, se reintenta cada 30 segundos sin iniciar ciclos.
# Una READY no adoptable no interrumpe la ejecución de la versión EFFECTIVE.
# Recovery y la propiedad del lease siguen siendo responsabilidad de JobComposition.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ada_command_center.alarms.materialization.local_reader import (
    AlarmMaterializationPublicationError,
)
from ada_command_center.processes.alarms_runtime.adoption import plan_configuration_adoption
from ada_command_center.processes.alarms_runtime.adoption_execution import (
    AlarmConfigurationAdoptionExecutor,
)
from ada_command_center.processes.alarms_runtime.job_composition import (
    AlarmRuntimeJobAdoptionOutcome,
    AlarmRuntimeJobIterationResult,
)
from ada_command_center.processes.alarms_runtime.local_configuration import (
    RuntimeEffectiveConfiguration,
    RuntimeEffectiveConfigurationError,
    RuntimeLocalConfigurationReader,
    build_alarm_configuration_revision,
)
from ada_command_center.processes.alarms_runtime.session import (
    AlarmEvaluatorRegistry,
    AlarmExecutionSession,
)
from atlanticus.runtime import JobRuntimeContext

INITIAL_CONFIGURATION_RETRY_SECONDS = 30.0
_STATUS_MEMORY_KEY = 'ada_command_center.alarms.runtime.configuration.status'
_PINNED_MEMORY_KEY = 'ada_command_center.alarms.runtime.configuration.pinned'


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _adoption_id() -> str:
    return uuid4().hex


@dataclass(slots=True)
class AlarmConfiguredIterationExecutor:
    reader: RuntimeLocalConfigurationReader
    evaluator_registry: AlarmEvaluatorRegistry
    adoption_executor: AlarmConfigurationAdoptionExecutor
    run_cycle: Callable[[JobRuntimeContext, AlarmExecutionSession], bool | None]
    clock: Callable[[], datetime] = field(default=_utc_now)
    adoption_id_factory: Callable[[], str] = field(default=_adoption_id)

    def __post_init__(self) -> None:
        if not isinstance(self.reader, RuntimeLocalConfigurationReader):
            raise TypeError('reader must be RuntimeLocalConfigurationReader')
        if not isinstance(self.evaluator_registry, AlarmEvaluatorRegistry):
            raise TypeError('evaluator_registry must be AlarmEvaluatorRegistry')
        if not isinstance(self.adoption_executor, AlarmConfigurationAdoptionExecutor):
            raise TypeError('adoption_executor must be AlarmConfigurationAdoptionExecutor')
        if (
            self.reader.volume_path
            != self.adoption_executor.composition.runtime_configuration.volume_path
        ):
            raise ValueError('reader and adoption executor must share the same VOLUMEN_PATH')
        if not callable(self.run_cycle):
            raise TypeError('run_cycle must be callable')
        if not callable(self.clock):
            raise TypeError('clock must be callable')
        if not callable(self.adoption_id_factory):
            raise TypeError('adoption_id_factory must be callable')

    def execute(self, context: JobRuntimeContext) -> AlarmRuntimeJobIterationResult:
        if not isinstance(context, JobRuntimeContext):
            raise TypeError('context must be JobRuntimeContext')
        context.assert_lease_current()
        context.raise_if_cancelled()
        # Una sesión ya inmovilizada evita toda nueva lectura de READY y EFFECTIVE.
        pinned = context.get_memory(_PINNED_MEMORY_KEY)
        if pinned is not None:
            if not isinstance(pinned, RuntimeEffectiveConfiguration):
                raise TypeError('pinned configuration must be RuntimeEffectiveConfiguration')
            return self._run_pinned(context, pinned, AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED)
        persistence = self.adoption_executor.composition.durability.persistence
        selected = self.reader.load_effective_revision(
            persistence=persistence,
            evaluator_registry=self.evaluator_registry,
        )
        try:
            ready = self.reader.load_ready_candidate()
        except AlarmMaterializationPublicationError as error:
            if selected is None:
                # Sin EFFECTIVE se espera un READY válido: nunca se omite la validación.
                return self._wait_for_initial_configuration(
                    context,
                    status='waiting_for_valid_ready',
                    notice_key=('invalid_ready', str(error)),
                    severity='warning',
                    message='Initial READY is invalid; checking again in 30 seconds',
                )
            self._notice(
                context,
                ('invalid_ready', str(error)),
                'warning',
                'READY is invalid; continuing with EFFECTIVE',
            )
            return self._run_effective(context, selected, AlarmRuntimeJobAdoptionOutcome.REJECTED)

        if ready is None:
            if selected is None:
                return self._wait_for_initial_configuration(
                    context,
                    status='waiting_for_ready',
                    notice_key=('waiting',),
                    severity='info',
                    message='No EFFECTIVE or READY configuration; checking again in 30 seconds',
                )
            self._notice(
                context,
                ('effective', selected.revision.artifact_ref.result_id),
                'info',
                'Using confirmed EFFECTIVE configuration',
            )
            return self._run_effective(context, selected, AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED)

        if selected is not None and ready.result_id == selected.revision.artifact_ref.result_id:
            if ready.manifest_sha256 != selected.revision.artifact_ref.manifest_sha256:
                raise RuntimeEffectiveConfigurationError(
                    'READY result identity conflicts with the exact EFFECTIVE artifact'
                )
            self._notice(
                context,
                ('effective', selected.revision.artifact_ref.result_id),
                'info',
                'Using confirmed EFFECTIVE configuration',
            )
            return self._run_effective(context, selected, AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED)

        try:
            target = build_alarm_configuration_revision(
                candidate=ready,
                evaluator_registry=self.evaluator_registry,
            )
        except ValueError as error:
            if selected is None:
                return self._wait_for_initial_configuration(
                    context,
                    status='waiting_for_executable_ready',
                    notice_key=(
                        'unexecutable_ready',
                        ready.result_id,
                        ready.manifest_sha256,
                        str(error),
                    ),
                    severity='warning',
                    message='Initial READY cannot be executed; checking again in 30 seconds',
                )
            self._notice(
                context,
                ('invalid_candidate', ready.result_id, ready.manifest_sha256),
                'warning',
                'New READY cannot be executed; continuing with EFFECTIVE',
            )
            return self._run_effective(context, selected, AlarmRuntimeJobAdoptionOutcome.REJECTED)

        if selected is None:
            self.adoption_executor.bootstrap(
                context,
                target,
                effective_at=self._effective_at(),
                adoption_id=self.adoption_id_factory(),
            )
            outcome = AlarmRuntimeJobAdoptionOutcome.BOOTSTRAPPED
        else:
            plan = plan_configuration_adoption(selected.revision, target)
            if not plan.is_adoptable:
                rejected = ', '.join(
                    f'{change.identity.canonical_key}:{change.rejection_reason.value}'
                    for change in plan.rejected_changes
                )
                self._notice(
                    context,
                    ('rejected', ready.result_id, ready.manifest_sha256),
                    'warning',
                    f'New READY adoption rejected; continuing with EFFECTIVE: {rejected}',
                )
                return self._run_effective(
                    context, selected, AlarmRuntimeJobAdoptionOutcome.REJECTED
                )
            self.reader.assert_current_effective(persistence=persistence, selected=selected)
            self.adoption_executor.execute(
                context,
                plan,
                effective_at=self._effective_at(),
                adoption_id=self.adoption_id_factory(),
            )
            outcome = AlarmRuntimeJobAdoptionOutcome.ADOPTED

        selected = self.reader.load_effective_revision(
            persistence=persistence,
            evaluator_registry=self.evaluator_registry,
        )
        if selected is None or selected.revision.artifact_ref != target.artifact_ref:
            raise RuntimeEffectiveConfigurationError(
                'EFFECTIVE does not match the confirmed READY configuration'
            )
        self._notice(
            context,
            ('confirmed', target.artifact_ref.result_id, target.artifact_ref.manifest_sha256),
            'info',
            'Alarm configuration adoption confirmed',
        )
        return self._run_effective(context, selected, outcome)

    # La espera sólo opera antes del pin; el framework conserva su ventana y permite cancelar.
    def _wait_for_initial_configuration(
        self,
        context: JobRuntimeContext,
        *,
        status: str,
        notice_key: tuple[str, ...],
        severity: str,
        message: str,
    ) -> AlarmRuntimeJobIterationResult:
        context.set_next_iteration_delay(INITIAL_CONFIGURATION_RETRY_SECONDS)
        context.set_iteration_fact('alarm_configuration_status', status)
        self._notice(context, notice_key, severity, message)
        return AlarmRuntimeJobIterationResult(
            adoption_outcome=AlarmRuntimeJobAdoptionOutcome.NOT_REQUIRED,
            cycle_executed=False,
        )

    def _run_effective(
        self,
        context: JobRuntimeContext,
        selected: RuntimeEffectiveConfiguration,
        outcome: AlarmRuntimeJobAdoptionOutcome,
    ) -> AlarmRuntimeJobIterationResult:
        context.raise_if_cancelled()
        self.reader.assert_current_effective(
            persistence=self.adoption_executor.composition.durability.persistence,
            selected=selected,
        )
        # El pin se instala antes del primer ciclo, incluso si ese ciclo falla.
        context.set_memory(_PINNED_MEMORY_KEY, selected)
        return self._run_pinned(context, selected, outcome)

    def _run_pinned(
        self,
        context: JobRuntimeContext,
        pinned: RuntimeEffectiveConfiguration,
        outcome: AlarmRuntimeJobAdoptionOutcome,
    ) -> AlarmRuntimeJobIterationResult:
        context.raise_if_cancelled()
        # Un callback puede diferir de forma controlada el ciclo sin consumir fuentes.
        # None mantiene el comportamiento compatible de callbacks ya existentes.
        cycle_result = self.run_cycle(context, pinned.revision.session)
        if cycle_result is not None and not isinstance(cycle_result, bool):
            raise TypeError('run_cycle must return bool or None')
        return AlarmRuntimeJobIterationResult(
            adoption_outcome=outcome, cycle_executed=cycle_result is not False
        )

    def _effective_at(self) -> datetime:
        timestamp = self.clock()
        if not isinstance(timestamp, datetime):
            raise TypeError('clock must return datetime')
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            raise ValueError('clock must return timezone-aware UTC')
        return timestamp

    @staticmethod
    def _notice(
        context: JobRuntimeContext,
        status: tuple[str, ...],
        severity: str,
        message: str,
    ) -> None:
        if context.get_memory(_STATUS_MEMORY_KEY) == status:
            return
        context.set_memory(_STATUS_MEMORY_KEY, status)
        if severity == 'warning':
            context.logger.warning(message, event_name='alarms.runtime.configuration.status')
        else:
            context.logger.info(message, event_name='alarms.runtime.configuration.status')
