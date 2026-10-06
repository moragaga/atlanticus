from __future__ import annotations

import pytest

from ada.kpis.history import KpiHistorianAuthority
from ada.processes.kpi_historian.errors import KpiHistorianRepositoryError
from ada.processes.kpi_historian.job import KpiHistorianJob
from ada.processes.kpi_historian.models import KpiHistorianIterationStatus

from .support import (
    AuthorityStore,
    CommitStateReader,
    EvaluationReader,
    HistoryMaterializer,
    RollingMaterializer,
    RuntimeContextStub,
    batch,
    evaluation,
    watermark,
    write_result,
)


def _job(
    *,
    committed=None,
    authority=None,
    batches=(),
    materializer=None,
    rolling=None,
    events=None,
    reprocess_current=False,
):
    events = [] if events is None else events
    committed = watermark() if committed is None else committed
    materializer = (
        HistoryMaterializer(write_result(committed), events=events)
        if materializer is None
        else materializer
    )
    rolling = RollingMaterializer(events=events) if rolling is None else rolling
    authority_store = AuthorityStore(authority, events=events)
    return (
        KpiHistorianJob(
            kpi_state=CommitStateReader(committed),
            evaluations=EvaluationReader(tuple(batches)),
            authority=authority_store,
            history=materializer,
            rolling=rolling,
            reprocess_current=reprocess_current,
        ),
        authority_store,
        materializer,
        rolling,
        events,
    )


def test_missing_kpi_watermark_is_empty() -> None:
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(None),
        evaluations=EvaluationReader(()),
        authority=AuthorityStore(),
        history=HistoryMaterializer(write_result(watermark())),
        rolling=RollingMaterializer(),
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.KPI_WATERMARK_MISSING
    assert context.iteration_facts['outcome'] == 'empty'
    assert context.work is False


def test_current_authority_skips_when_rolling_is_coherent() -> None:
    current = watermark(2)
    reader = EvaluationReader(())
    authority = AuthorityStore(KpiHistorianAuthority(current.timestamp_utc))
    rolling = RollingMaterializer(coherent=True)
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(current),
        evaluations=reader,
        authority=authority,
        history=HistoryMaterializer(write_result(current)),
        rolling=rolling,
    )

    result = job.run_iteration(RuntimeContextStub())

    assert result.status is KpiHistorianIterationStatus.SKIPPED_CURRENT
    assert reader.calls == 0
    assert rolling.coherence_calls == 1
    assert rolling.rebuild_calls == 0


def test_current_authority_rebuilds_incoherent_rolling_without_reprocessing_history() -> None:
    current = watermark(2)
    reader = EvaluationReader(())
    history = HistoryMaterializer(write_result(current))
    rolling = RollingMaterializer(coherent=False)
    authority = AuthorityStore(KpiHistorianAuthority(current.timestamp_utc))
    context = RuntimeContextStub()
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(current),
        evaluations=reader,
        authority=authority,
        history=history,
        rolling=rolling,
    )

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.PROCESSED
    assert reader.calls == 0
    assert history.calls == 0
    assert rolling.rebuild_calls == 1
    assert authority.commit_calls == 0
    assert context.work is True


def test_current_authority_reprocesses_from_beginning_when_enabled() -> None:
    first = watermark(1)
    current = watermark(2)
    batches = (
        batch(evaluation('a', watermark_value=first)),
        batch(evaluation('a', watermark_value=current)),
    )
    reader = EvaluationReader(batches)
    materializer = HistoryMaterializer(
        write_result(
            current,
            batches_processed=2,
            evaluations_processed=2,
            history_rows=2,
        )
    )
    rolling = RollingMaterializer()
    authority = AuthorityStore(KpiHistorianAuthority(current.timestamp_utc))
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(current),
        evaluations=reader,
        authority=authority,
        history=materializer,
        rolling=rolling,
        reprocess_current=True,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.PROCESSED
    assert reader.after is None
    assert reader.through == current
    assert materializer.batches == batches
    assert rolling.batches == batches
    assert rolling.previous_authority == KpiHistorianAuthority(current.timestamp_utc)
    assert authority.commit_calls == 1
    assert authority.value == KpiHistorianAuthority(current.timestamp_utc)
    assert context.fences == 1
    assert context.work is True


def test_current_reprocess_requires_persisted_batches() -> None:
    current = watermark(2)
    job, _, _, _, _ = _job(
        committed=current,
        authority=KpiHistorianAuthority(current.timestamp_utc),
        reprocess_current=True,
    )

    with pytest.raises(KpiHistorianRepositoryError, match='no persisted evaluation batch'):
        job.run_iteration(RuntimeContextStub())


def test_reprocess_current_does_not_change_incremental_catch_up() -> None:
    before = watermark(1)
    committed = watermark(2)
    reader = EvaluationReader((batch(evaluation('a', watermark_value=committed)),))
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(committed),
        evaluations=reader,
        authority=AuthorityStore(KpiHistorianAuthority(before.timestamp_utc)),
        history=HistoryMaterializer(write_result(committed)),
        rolling=RollingMaterializer(),
        reprocess_current=True,
    )

    job.run_iteration(RuntimeContextStub())

    assert reader.after == before
    assert reader.through == committed


def test_authority_ahead_of_kpi_is_rejected() -> None:
    job, _, _, _, _ = _job(
        committed=watermark(1),
        authority=KpiHistorianAuthority(watermark(2).timestamp_utc),
    )

    with pytest.raises(KpiHistorianRepositoryError, match='must not regress'):
        job.run_iteration(RuntimeContextStub())


def test_authority_ahead_of_kpi_is_rejected_when_reprocess_is_enabled() -> None:
    job, _, _, _, _ = _job(
        committed=watermark(1),
        authority=KpiHistorianAuthority(watermark(2).timestamp_utc),
        reprocess_current=True,
    )

    with pytest.raises(KpiHistorianRepositoryError, match='must not regress'):
        job.run_iteration(RuntimeContextStub())


def test_missing_persisted_range_is_rejected() -> None:
    job, _, _, _, _ = _job(committed=watermark(2), batches=())

    with pytest.raises(KpiHistorianRepositoryError, match='no persisted evaluation batch'):
        job.run_iteration(RuntimeContextStub())


def test_range_must_reach_committed_watermark() -> None:
    first = watermark(1)
    job, _, _, _, _ = _job(
        committed=watermark(2),
        batches=(batch(evaluation('a', watermark_value=first)),),
    )

    with pytest.raises(KpiHistorianRepositoryError, match='does not reach'):
        job.run_iteration(RuntimeContextStub())


def test_materialize_history_then_rolling_then_commit_authority_last() -> None:
    committed = watermark(2)
    current_batch = batch(evaluation('a', watermark_value=committed))
    events: list[str] = []
    job, authority, materializer, rolling, _ = _job(
        committed=committed,
        batches=(current_batch,),
        events=events,
    )
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.status is KpiHistorianIterationStatus.PROCESSED
    assert events == ['history', 'rolling', 'authority']
    assert authority.value is not None
    assert authority.value.watermark_utc == committed.timestamp_utc
    assert materializer.batches == (current_batch,)
    assert rolling.batches == (current_batch,)
    assert rolling.previous_authority is None
    assert context.fences == 1
    assert context.work is True
    assert context.execution_counters['batches_processed'] == 1


def test_history_materialization_failure_never_writes_rolling_or_commits_authority() -> None:
    committed = watermark(2)
    events: list[str] = []
    materializer = HistoryMaterializer(write_result(committed), events=events)
    materializer.error = RuntimeError('write failed')
    rolling = RollingMaterializer(events=events)
    job, authority, _, _, _ = _job(
        committed=committed,
        batches=(batch(evaluation('a', watermark_value=committed)),),
        materializer=materializer,
        rolling=rolling,
        events=events,
    )

    with pytest.raises(RuntimeError, match='write failed'):
        job.run_iteration(RuntimeContextStub())

    assert authority.commit_calls == 0
    assert rolling.materialize_calls == 0
    assert events == ['history']


def test_rolling_failure_never_commits_authority() -> None:
    committed = watermark(2)
    events: list[str] = []
    rolling = RollingMaterializer(events=events)
    rolling.error = RuntimeError('rolling failed')
    job, authority, _, _, _ = _job(
        committed=committed,
        batches=(batch(evaluation('a', watermark_value=committed)),),
        rolling=rolling,
        events=events,
    )

    with pytest.raises(RuntimeError, match='rolling failed'):
        job.run_iteration(RuntimeContextStub())

    assert authority.commit_calls == 0
    assert events == ['history', 'rolling']


def test_existing_authority_is_passed_as_read_after_and_rolling_boundary() -> None:
    before = watermark(1)
    committed = watermark(2)
    reader = EvaluationReader((batch(evaluation('a', watermark_value=committed)),))
    rolling = RollingMaterializer()
    job = KpiHistorianJob(
        kpi_state=CommitStateReader(committed),
        evaluations=reader,
        authority=AuthorityStore(KpiHistorianAuthority(before.timestamp_utc)),
        history=HistoryMaterializer(write_result(committed)),
        rolling=rolling,
    )

    job.run_iteration(RuntimeContextStub())

    assert reader.after == before
    assert reader.through == committed
    assert rolling.previous_authority == KpiHistorianAuthority(before.timestamp_utc)


def test_constructor_rejects_non_boolean_reprocess_current() -> None:
    with pytest.raises(TypeError, match='reprocess_current must be bool'):
        KpiHistorianJob(
            kpi_state=CommitStateReader(watermark()),
            evaluations=EvaluationReader(()),
            authority=AuthorityStore(),
            history=HistoryMaterializer(write_result(watermark())),
            rolling=RollingMaterializer(),
            reprocess_current='true',
        )
