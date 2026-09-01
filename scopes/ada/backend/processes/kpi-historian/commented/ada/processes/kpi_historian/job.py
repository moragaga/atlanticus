# Orquesta autoridad upstream, materialización y commit final sin acoplarse a otro proceso.
from __future__ import annotations

from typing import Protocol

from ada.kpis.core import KpiWatermark
from ada.kpis.history import KpiHistorianAuthority, historian_watermark_text
from ada.kpis.persistence import KpiCommitState, KpiEvaluationBatch
from ada.processes.kpi_historian.errors import KpiHistorianRepositoryError
from ada.processes.kpi_historian.models import (
    KpiHistorianIterationResult,
    KpiHistorianIterationStatus,
    KpiHistorianWriteResult,
)
from atlanticus.runtime import JobRuntimeContext

_UNSET = object()


class _CommitStateReader(Protocol):
    def read(self) -> KpiCommitState: ...


class _EvaluationReader(Protocol):
    def read_after(
        self,
        *,
        after: KpiWatermark | None,
        through: KpiWatermark,
    ) -> tuple[KpiEvaluationBatch, ...]: ...


class _AuthorityStore(Protocol):
    def read(self) -> KpiHistorianAuthority | None: ...

    def commit(self, authority: KpiHistorianAuthority) -> KpiHistorianAuthority: ...


class _HistoryMaterializer(Protocol):
    def materialize(self, *, batches, check_current=None) -> KpiHistorianWriteResult: ...


class KpiHistorianJob:
    def __init__(
        self,
        *,
        kpi_state: _CommitStateReader,
        evaluations: _EvaluationReader,
        authority: _AuthorityStore,
        history: _HistoryMaterializer,
    ) -> None:
        for value, method_name, field_name in (
            (kpi_state, 'read', 'kpi_state'),
            (evaluations, 'read_after', 'evaluations'),
            (authority, 'read', 'authority'),
            (authority, 'commit', 'authority'),
            (history, 'materialize', 'history'),
        ):
            if not callable(getattr(value, method_name, None)):
                raise TypeError(f'{field_name} must provide a callable {method_name} method')
        self._kpi_state = kpi_state
        self._evaluations = evaluations
        self._authority_store = authority
        self._history = history
        self._authority: KpiHistorianAuthority | None | object = _UNSET

    def run_iteration(self, context: JobRuntimeContext) -> KpiHistorianIterationResult:
        context.raise_if_cancelled()
        historian_before = self._current_authority()
        committed = self._kpi_state.read().watermark
        _validate_authority(historian_before=historian_before, committed=committed)

        if committed is None:
            return _record_result(
                context,
                KpiHistorianIterationResult(
                    status=KpiHistorianIterationStatus.KPI_WATERMARK_MISSING,
                ),
            )

        if historian_before is not None and historian_before.watermark_utc == committed.timestamp_utc:
            return _record_result(
                context,
                KpiHistorianIterationResult(
                    status=KpiHistorianIterationStatus.SKIPPED_CURRENT,
                    kpi_committed_watermark_utc=committed.to_text(),
                    historian_before_watermark_utc=committed.to_text(),
                    historian_after_watermark_utc=committed.to_text(),
                    historian_revision=historian_before.revision,
                ),
            )

        after = (
            None
            if historian_before is None
            else KpiWatermark(historian_before.watermark_utc)
        )
        batches = self._evaluations.read_after(after=after, through=committed)
        if not batches:
            raise KpiHistorianRepositoryError(
                'KPI committed watermark has no persisted evaluation batch for historian'
            )
        if batches[-1].watermark != committed:
            raise KpiHistorianRepositoryError(
                'KPI historian evaluation range does not reach the committed watermark'
            )

        def check_current() -> None:
            context.raise_if_cancelled()
            context.assert_lease_current()

        write_result = self._history.materialize(
            batches=batches,
            check_current=check_current,
        )
        if write_result.last_watermark_utc != committed.to_text():
            raise KpiHistorianRepositoryError(
                'KPI historian materialization does not reach the committed watermark'
            )

        check_current()
        new_authority = KpiHistorianAuthority(watermark_utc=committed.timestamp_utc)
        with context.fenced_mutation():
            historian_after = self._authority_store.commit(new_authority)
        self._authority = historian_after
        return _record_result(
            context,
            KpiHistorianIterationResult(
                status=KpiHistorianIterationStatus.PROCESSED,
                kpi_committed_watermark_utc=committed.to_text(),
                historian_before_watermark_utc=(
                    None
                    if historian_before is None
                    else historian_watermark_text(historian_before.watermark_utc)
                ),
                historian_after_watermark_utc=historian_watermark_text(
                    historian_after.watermark_utc
                ),
                historian_revision=historian_after.revision,
                batches_processed=write_result.batches_processed,
                evaluations_processed=write_result.evaluations_processed,
                history_rows=write_result.history_rows,
                error_rows=write_result.error_rows,
                history_publications=write_result.history_publications,
                error_publications=write_result.error_publications,
            ),
        )

    def _current_authority(self) -> KpiHistorianAuthority | None:
        if self._authority is _UNSET:
            self._authority = self._authority_store.read()
        if self._authority is None:
            return None
        return self._authority


def _validate_authority(
    *,
    historian_before: KpiHistorianAuthority | None,
    committed: KpiWatermark | None,
) -> None:
    if historian_before is None:
        return
    if committed is None:
        raise KpiHistorianRepositoryError(
            'KPI committed watermark is missing after historian progress'
        )
    if historian_before.watermark_utc > committed.timestamp_utc:
        raise KpiHistorianRepositoryError(
            'KPI committed watermark must not regress behind historian authority'
        )


def _record_result(
    context: JobRuntimeContext, result: KpiHistorianIterationResult
) -> KpiHistorianIterationResult:
    if result.status is KpiHistorianIterationStatus.KPI_WATERMARK_MISSING:
        outcome = 'empty'
    elif result.status is KpiHistorianIterationStatus.SKIPPED_CURRENT:
        outcome = 'skipped'
    else:
        outcome = 'completed'
    context.set_iteration_fact('outcome', outcome)
    context.set_iteration_fact('reason', result.status.value)
    if result.kpi_committed_watermark_utc is not None:
        context.set_iteration_fact(
            'kpi_committed_watermark_utc', result.kpi_committed_watermark_utc
        )
        context.set_execution_fact(
            'kpi_committed_watermark_utc', result.kpi_committed_watermark_utc
        )
    if result.historian_before_watermark_utc is not None:
        context.set_iteration_fact(
            'historian_before_watermark_utc', result.historian_before_watermark_utc
        )
    if result.historian_after_watermark_utc is not None:
        context.set_iteration_fact(
            'historian_after_watermark_utc', result.historian_after_watermark_utc
        )
        context.set_execution_fact(
            'historian_committed_watermark_utc', result.historian_after_watermark_utc
        )
    if result.historian_revision is not None:
        context.set_iteration_fact('historian_revision', result.historian_revision)
        context.set_execution_fact('historian_revision', result.historian_revision)
    if outcome == 'completed':
        facts = {
            'batches_processed': result.batches_processed,
            'evaluations_processed': result.evaluations_processed,
            'history_rows': result.history_rows,
            'error_rows': result.error_rows,
            'history_publications': result.history_publications,
            'error_publications': result.error_publications,
        }
        for key, value in facts.items():
            context.set_iteration_fact(key, value)
            context.increment_execution_counter(key, value)
        context.mark_iteration_work()
    return result
