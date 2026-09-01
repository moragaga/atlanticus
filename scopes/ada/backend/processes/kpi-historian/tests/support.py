from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

from ada.kpis.core import (
    KpiEvaluation,
    KpiResult,
    KpiStatus,
    KpiValueKind,
    KpiValueType,
    KpiWatermark,
)
from ada.kpis.history import KpiHistorianAuthority
from ada.kpis.persistence import KpiCommitState, KpiEvaluationBatch
from ada.processes.kpi_historian.models import KpiHistorianWriteResult


class RuntimeContextStub:
    def __init__(self) -> None:
        self.iteration_facts: dict[str, object] = {}
        self.execution_facts: dict[str, object] = {}
        self.execution_counters: dict[str, float] = {}
        self.work = False
        self.cancel_checks = 0
        self.lease_checks = 0
        self.fences = 0

    def raise_if_cancelled(self) -> None:
        self.cancel_checks += 1

    def assert_lease_current(self) -> None:
        self.lease_checks += 1

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield

    def mark_iteration_work(self) -> None:
        self.work = True

    def set_iteration_fact(self, key: str, value: object) -> None:
        self.iteration_facts[key] = value

    def set_execution_fact(self, key: str, value: object) -> None:
        self.execution_facts[key] = value

    def increment_execution_counter(self, key: str, amount: int | float = 1) -> None:
        self.execution_counters[key] = self.execution_counters.get(key, 0) + amount


class CommitStateReader:
    def __init__(self, watermark: KpiWatermark | None) -> None:
        self.watermark = watermark
        self.calls = 0

    def read(self) -> KpiCommitState:
        self.calls += 1
        return KpiCommitState(self.watermark)


class EvaluationReader:
    def __init__(self, batches: tuple[KpiEvaluationBatch, ...]) -> None:
        self.batches = batches
        self.calls = 0
        self.after = None
        self.through = None

    def read_after(self, *, after, through) -> tuple[KpiEvaluationBatch, ...]:
        self.calls += 1
        self.after = after
        self.through = through
        return self.batches


class AuthorityStore:
    def __init__(self, value: KpiHistorianAuthority | None = None, events=None) -> None:
        self.value = value
        self.read_calls = 0
        self.commit_calls = 0
        self.events = [] if events is None else events

    def read(self) -> KpiHistorianAuthority | None:
        self.read_calls += 1
        return self.value

    def commit(self, authority: KpiHistorianAuthority) -> KpiHistorianAuthority:
        self.commit_calls += 1
        self.events.append('authority')
        self.value = authority
        return authority


class HistoryMaterializer:
    def __init__(self, result: KpiHistorianWriteResult, events=None) -> None:
        self.result = result
        self.calls = 0
        self.batches = ()
        self.events = [] if events is None else events
        self.error: Exception | None = None

    def materialize(self, *, batches, check_current=None) -> KpiHistorianWriteResult:
        self.calls += 1
        self.batches = tuple(batches)
        self.events.append('history')
        if check_current is not None:
            check_current()
        if self.error is not None:
            raise self.error
        return self.result


def watermark(minute: int = 0) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 9, 1, 5, minute, tzinfo=UTC))


def evaluation(
    key: str,
    *,
    watermark_value: KpiWatermark | None = None,
    status: KpiStatus = KpiStatus.OK,
    value_kind: KpiValueKind = KpiValueKind.VALUE,
    value='42.5',
    parsed_value=None,
    value_type: KpiValueType | None = KpiValueType.FLOAT,
    error: str | None = None,
    persist_history: bool = True,
) -> KpiEvaluation:
    resolved = watermark() if watermark_value is None else watermark_value
    if value_kind is KpiValueKind.JSON:
        value_type = None
        parsed_value = None
    elif status is KpiStatus.OK:
        if not isinstance(value, str):
            value = str(value)
        if parsed_value is None:
            parsed_value = value.replace('.', ',')
    if status is KpiStatus.OK:
        result = KpiResult(
            status=status,
            value_kind=value_kind,
            value=value,
            parsed_value=parsed_value,
            value_type=value_type,
        )
    elif status is KpiStatus.MISSING:
        result = KpiResult(status=status, value_kind=value_kind, value_type=value_type)
    else:
        result = KpiResult(
            status=status,
            value_kind=value_kind,
            value_type=value_type,
            error='TestError' if error is None else error,
        )
    return KpiEvaluation(
        key=key,
        area='general',
        watermark=resolved,
        evaluated_at_utc=resolved.timestamp_utc,
        result=result,
        persist_history=persist_history,
    )


def batch(*evaluations: KpiEvaluation) -> KpiEvaluationBatch:
    return KpiEvaluationBatch(watermark=evaluations[0].watermark, evaluations=evaluations)


def write_result(watermark_value: KpiWatermark, **overrides) -> KpiHistorianWriteResult:
    values = {
        'batches_processed': 1,
        'evaluations_processed': 1,
        'history_rows': 1,
        'error_rows': 0,
        'history_publications': 1,
        'error_publications': 0,
        'last_watermark_utc': watermark_value.to_text(),
    }
    values.update(overrides)
    return KpiHistorianWriteResult(**values)
