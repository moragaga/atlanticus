# Espejo pedagógico: explica el orden durable batch→watermark y la idempotencia sin alterar la semántica.
from __future__ import annotations

from pathlib import Path

from ada.kpis.core import KpiWatermark
from ada.kpis.persistence.errors import KpiPersistenceError, KpiPersistenceOrderError
from ada.kpis.persistence.models import KpiCommitResult, KpiCommitState, KpiEvaluationBatch
from ada.kpis.persistence.paths import KpiPersistencePaths
from ada.kpis.persistence.repositories import KpiEvaluationRepository
from ada.kpis.persistence.state import KpiCommitStateRepository
from atlanticus.json import JsonConflictError
from atlanticus.state import AtomicStateStore


class KpiPersistence:
    def __init__(
        self,
        *,
        evaluations: KpiEvaluationRepository,
        state: KpiCommitStateRepository,
    ) -> None:
        if not isinstance(evaluations, KpiEvaluationRepository):
            raise TypeError('evaluations must be KpiEvaluationRepository')
        if not isinstance(state, KpiCommitStateRepository):
            raise TypeError('state must be KpiCommitStateRepository')
        self._evaluations = evaluations
        self._state = state

    @classmethod
    def from_runtime(cls, *, volume_path: str | Path, application: str) -> KpiPersistence:
        state_store = AtomicStateStore(volume_path=volume_path, application=application)
        state = KpiCommitStateRepository(state_store)
        evaluations = KpiEvaluationRepository(
            paths=KpiPersistencePaths(state_store.application_root)
        )
        return cls(evaluations=evaluations, state=state)

    def committed_watermark(self) -> KpiWatermark | None:
        return self._state.read().watermark

    def commit(self, batch: KpiEvaluationBatch) -> KpiCommitResult:
        if not isinstance(batch, KpiEvaluationBatch):
            raise TypeError('batch must be KpiEvaluationBatch')
        before = self._state.read().watermark
        if before is not None and batch.watermark < before:
            raise KpiPersistenceOrderError('KPI commit watermark must not move backwards')
        try:
            status = self._evaluations.write_once(batch)
        except JsonConflictError as error:
            raise KpiPersistenceError(
                'KPI evaluation batch conflicts with durable content'
            ) from error
        if before != batch.watermark:
            self._state.replace(KpiCommitState(batch.watermark))
        return KpiCommitResult(before=before, after=batch.watermark, write_status=status)

    def read_committed_after(
        self,
        after: KpiWatermark | None = None,
    ) -> tuple[KpiEvaluationBatch, ...]:
        through = self.committed_watermark()
        if through is None:
            return ()
        return self._evaluations.read_after(after=after, through=through)
