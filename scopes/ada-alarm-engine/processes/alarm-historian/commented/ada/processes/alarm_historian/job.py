from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ada.alarms.history import AlarmHistoryMaterializer
from ada.processes.alarm_historian.checkpoint import AlarmHistorianCheckpointStore
from ada.processes.alarm_historian.reader import AlarmHistorianReader
from atlanticus.runtime import JobRuntimeContext



# Contrato mínimo del destino: no obliga a conocer su almacenamiento físico.
class _DatasetMerger(Protocol):
    def merge(self, **kwargs): ...



# Adaptador con estado por iteración: cada merge adquiere su propio fencing.
# No llamar a assert_lease_current() dentro del fence; ambos usan la misma exclusión.
class _FencedDatasetMerger:
    def __init__(self, *, runtime: _DatasetMerger, context: JobRuntimeContext) -> None:
        self._runtime = runtime
        self._context = context

    def merge(self, **kwargs):
        # Comprobar cancelación antes de entrar a la sección protegida.
        self._context.raise_if_cancelled()
        with self._context.fenced_mutation():
            return self._runtime.merge(**kwargs)


@dataclass(frozen=True, slots=True)

# Resultado funcional de un lote, separado del ciclo de vida del proceso ejecutable.
class AlarmHistorianIterationResult:
    records_read: int
    facts_projected: int
    facts_excluded: int
    targets_committed: int
    targets_unchanged: int
    checkpoint_advanced: bool



# Orquesta una iteración sin crear schedulers, workers ni recursos remotos.
class AlarmHistorianJob:
    def __init__(
        self,
        *,
        reader: AlarmHistorianReader,
        checkpoint: AlarmHistorianCheckpointStore,
        runtime: _DatasetMerger,
    ) -> None:
        if not isinstance(reader, AlarmHistorianReader):
            raise TypeError('reader must be an AlarmHistorianReader')
        if not isinstance(checkpoint, AlarmHistorianCheckpointStore):
            raise TypeError('checkpoint must be an AlarmHistorianCheckpointStore')
        if not callable(getattr(runtime, 'merge', None)):
            raise TypeError('runtime must provide a callable merge method')
        self._reader = reader
        self._checkpoint = checkpoint
        self._runtime = runtime

    def run_iteration(self, context: JobRuntimeContext) -> AlarmHistorianIterationResult:
        context.raise_if_cancelled()
        context.assert_lease_current()
        # Nunca avanzar el lector sin recuperar previamente la posición durable.
        previous = self._checkpoint.read()
        batch = self._reader.read(after=None if previous is None else previous.position)
        context.raise_if_cancelled()
        # No hay publicación ni mutación cuando el lector no entrega nuevos registros.
        if batch.records_read == 0:
            result = AlarmHistorianIterationResult(0, 0, 0, 0, 0, False)
            self._record(context, result)
            return result
        if batch.last_position is None:
            raise ValueError('Historian batch has no confirmed final position')

        # El materializador confirma cada destino antes de devolver el resultado global.
        # El adaptador protege cada merge individual, sin bloquear todo el lote.
        materializer = AlarmHistoryMaterializer(
            runtime=_FencedDatasetMerger(runtime=self._runtime, context=context)
        )
        published = materializer.materialize(
            facts=batch.facts,
            check_current=context.assert_lease_current,
        )
        context.raise_if_cancelled()
        # Confirmar la posición en un fence independiente, posterior a todos los merges.
        # Si esta escritura falla, el replay vuelve a materializar sin duplicar hechos.
        with context.fenced_mutation():
            self._checkpoint.save(batch.last_position)

        result = AlarmHistorianIterationResult(
            records_read=batch.records_read,
            facts_projected=published.facts_unique,
            facts_excluded=batch.excluded_count,
            targets_committed=published.targets_committed,
            targets_unchanged=published.targets_unchanged,
            checkpoint_advanced=True,
        )
        # Registrar trabajo solo después del checkpoint exitoso, incluso si todo fue excluido.
        context.mark_iteration_work()
        self._record(context, result)
        return result

    @staticmethod
    def _record(context: JobRuntimeContext, result: AlarmHistorianIterationResult) -> None:
        # Exponer contadores de lote para observabilidad y qualification.
        context.set_iteration_fact('records_read', result.records_read)
        context.set_iteration_fact('facts_projected', result.facts_projected)
        context.set_iteration_fact('facts_excluded', result.facts_excluded)
        context.set_iteration_fact('targets_committed', result.targets_committed)
        context.set_iteration_fact('targets_unchanged', result.targets_unchanged)
        context.set_iteration_fact('checkpoint_advanced', result.checkpoint_advanced)
