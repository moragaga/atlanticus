from __future__ import annotations

import pytest

from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_historian.errors import KpiHistorianRepositoryError
from ada.processes.kpi_historian.job import KpiHistorianJob
from ada.processes.kpi_historian.models import KpiHistorianIterationStatus
from tests.support import (
    AuthorityStore,
    CommitStateReader,
    EvaluationReader,
    HistoryMaterializer,
    RuntimeContextStub,
    batch,
    evaluation,
    watermark,
    write_result,
)


def _job(*, committed=None, authority=None, batches=(), materializer=None, events=None):
    events = [] if events is None else events
    committed = watermark() if committed is None else committed
    materializer = (
        HistoryMaterializer(write_result(committed), events=events)
        if materializer is None
        else materializer
    )
    authority_store = AuthorityStore(authority, events=events)
    return (
        KpiHistorianJob(
            kpi_state=CommitStateReader(committed),
            evaluations=EvaluationReader(tuple(batches)),
            authority=authority_store,
            history=materializer,
        ),
        authority_store,
        materializer,
        events,
    )


def test_missing_kpi_watermark_is_empty() -> None:
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(None),
        evaluations=EvaluationReader(()),
        authority=AuthorityStore(),
        history=HistoryMaterializer(write_result(watermark())),
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.KPI_WATERMARK_MISSING
    assert context.iteration_facts['outcome'] == 'empty'
    assert context.work is False


def test_current_authority_skips_without_reading_evaluations() -> None:
    current = watermark(2)
    reader = EvaluationReader(())
    authority = AuthorityStore(KpiHistorianAuthority(current.timestamp_utc))
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(current),
        evaluations=reader,
        authority=authority,
        history=HistoryMaterializer(write_result(current)),
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiHistorianIterationStatus.SKIPPED_CURRENT
    assert reader.calls == 0


def test_authority_ahead_of_kpi_is_rejected() -> None:
    job, _, _, _ = _job(
        committed=watermark(1),
        authority=KpiHistorianAuthority(watermark(2).timestamp_utc),
    )

    with pytest.raises(KpiHistorianRepositoryError, match='must not regress'):
        job.run_iteration(RuntimeContextStub())


def test_missing_persisted_range_is_rejected() -> None:
    job, _, _, _ = _job(committed=watermark(2), batches=())

    with pytest.raises(KpiHistorianRepositoryError, match='no persisted evaluation batch'):
        job.run_iteration(RuntimeContextStub())


def test_range_must_reach_committed_watermark() -> None:
    first = watermark(1)
    job, _, _, _ = _job(
        committed=watermark(2),
        batches=(batch(evaluation('a', watermark_value=first)),),
    )

    with pytest.raises(KpiHistorianRepositoryError, match='does not reach'):
        job.run_iteration(RuntimeContextStub())


def test_materialize_then_commit_authority_last() -> None:
    committed = watermark(2)
    current_batch = batch(evaluation('a', watermark_value=committed))
    events: list[str] = []
    job, authority, materializer, _ = _job(
        committed=committed,
        batches=(current_batch,),
        events=events,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.PROCESSED
    assert events == ['history', 'authority']
    assert authority.value is not None
    assert authority.value.watermark_utc == committed.timestamp_utc
    assert materializer.batches == (current_batch,)
    assert context.fences == 1
    assert context.work is True
    assert context.execution_counters['batches_processed'] == 1


def test_materialization_failure_never_commits_authority() -> None:
    committed = watermark(2)
    events: list[str] = []
    materializer = HistoryMaterializer(write_result(committed), events=events)
    materializer.error = RuntimeError('write failed')
    job, authority, _, _ = _job(
        committed=committed,
        batches=(batch(evaluation('a', watermark_value=committed)),),
        materializer=materializer,
        events=events,
    )

    with pytest.raises(RuntimeError, match='write failed'):
        job.run_iteration(RuntimeContextStub())

    assert authority.commit_calls == 0
    assert events == ['history']


def test_existing_authority_is_passed_as_read_after_boundary() -> None:
    before = watermark(1)
    committed = watermark(2)
    reader = EvaluationReader((batch(evaluation('a', watermark_value=committed)),))
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(committed),
        evaluations=reader,
        authority=AuthorityStore(KpiHistorianAuthority(before.timestamp_utc)),
        history=HistoryMaterializer(write_result(committed)),
    )

    job.run_iteration(RuntimeContextStub())

    assert reader.after == before
    assert reader.through == committed
