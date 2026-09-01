from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol

import pyarrow as pa

from ada.kpis.core import KpiEvaluation, KpiStatus, KpiWatermark
from ada.kpis.history import (
    HISTORY_KEY_COLUMNS,
    HISTORY_ORDER_COLUMNS,
    encode_history_value,
    error_history_definition,
    error_history_schema,
    error_history_target,
    history_definition,
    history_schema,
    history_target,
)
from ada.kpis.persistence import KpiEvaluationBatch
from ada.processes.kpi_historian.errors import KpiHistorianHistoryError
from ada.processes.kpi_historian.models import KpiHistorianWriteResult


class _DatasetMerger(Protocol):
    def merge(self, **kwargs): ...


class KpiHistorianMaterializer:
    def __init__(self, *, runtime: _DatasetMerger) -> None:
        if not callable(getattr(runtime, 'merge', None)):
            raise TypeError('runtime must provide a callable merge method')
        self._runtime = runtime

    def materialize(
        self,
        *,
        batches: Iterable[KpiEvaluationBatch],
        check_current: Callable[[], None] | None = None,
    ) -> KpiHistorianWriteResult:
        if isinstance(batches, KpiEvaluationBatch | str | bytes):
            raise TypeError('batches must be an iterable of KpiEvaluationBatch values')
        if check_current is not None and not callable(check_current):
            raise TypeError('check_current must be callable or None')
        try:
            iterator = iter(batches)
        except TypeError as error:
            raise TypeError('batches must be an iterable of KpiEvaluationBatch values') from error

        current_day: date | None = None
        history_records: list[dict[str, object]] = []
        error_records: list[dict[str, object]] = []
        previous: KpiWatermark | None = None
        batches_processed = 0
        evaluations_processed = 0
        history_rows = 0
        error_rows = 0
        history_publications = 0
        error_publications = 0

        for batch in iterator:
            _check_current(check_current)
            if not isinstance(batch, KpiEvaluationBatch):
                raise TypeError('batches must contain KpiEvaluationBatch values')
            if previous is not None and batch.watermark <= previous:
                raise KpiHistorianHistoryError('KPI evaluation batches must be strictly ordered')

            batch_day = batch.watermark.timestamp_utc.date()
            if current_day is not None and batch_day != current_day:
                history_count, error_count = self._flush(
                    day=current_day,
                    history_records=history_records,
                    error_records=error_records,
                    check_current=check_current,
                )
                history_publications += history_count
                error_publications += error_count
                history_records = []
                error_records = []
            current_day = batch_day

            for evaluation in batch.evaluations:
                evaluations_processed += 1
                if evaluation.persist_history:
                    history_records.append(_history_record(evaluation))
                    history_rows += 1
                if evaluation.status is KpiStatus.ERROR:
                    error_records.append(_error_record(evaluation))
                    error_rows += 1
            batches_processed += 1
            previous = batch.watermark

        if current_day is not None:
            history_count, error_count = self._flush(
                day=current_day,
                history_records=history_records,
                error_records=error_records,
                check_current=check_current,
            )
            history_publications += history_count
            error_publications += error_count

        return KpiHistorianWriteResult(
            batches_processed=batches_processed,
            evaluations_processed=evaluations_processed,
            history_rows=history_rows,
            error_rows=error_rows,
            history_publications=history_publications,
            error_publications=error_publications,
            last_watermark_utc=None if previous is None else previous.to_text(),
        )

    def _flush(
        self,
        *,
        day: date,
        history_records: list[dict[str, object]],
        error_records: list[dict[str, object]],
        check_current: Callable[[], None] | None,
    ) -> tuple[int, int]:
        history_publications = self._merge_history(
            day=day,
            records=history_records,
            check_current=check_current,
        )
        error_publications = self._merge_errors(
            day=day,
            records=error_records,
            check_current=check_current,
        )
        return history_publications, error_publications

    def _merge_history(
        self,
        *,
        day: date,
        records: list[dict[str, object]],
        check_current: Callable[[], None] | None,
    ) -> int:
        if not records:
            return 0
        _check_current(check_current)
        table = pa.Table.from_pylist(records, schema=history_schema())
        self._runtime.merge(
            definition=history_definition(),
            target=history_target(day),
            data=table,
            key_columns=HISTORY_KEY_COLUMNS,
            order_by=HISTORY_ORDER_COLUMNS,
        )
        return 1

    def _merge_errors(
        self,
        *,
        day: date,
        records: list[dict[str, object]],
        check_current: Callable[[], None] | None,
    ) -> int:
        if not records:
            return 0
        _check_current(check_current)
        table = pa.Table.from_pylist(records, schema=error_history_schema())
        self._runtime.merge(
            definition=error_history_definition(),
            target=error_history_target(day),
            data=table,
            key_columns=HISTORY_KEY_COLUMNS,
            order_by=HISTORY_ORDER_COLUMNS,
        )
        return 1


def _history_record(evaluation: KpiEvaluation) -> dict[str, object]:
    return {
        'timestamp_utc': evaluation.watermark.timestamp_utc,
        'key': evaluation.key,
        'status': evaluation.status.value,
        'value_kind': evaluation.value_kind.value,
        'value': encode_history_value(evaluation.value),
        'parsed_value': encode_history_value(evaluation.parsed_value),
    }


def _error_record(evaluation: KpiEvaluation) -> dict[str, object]:
    if evaluation.status is not KpiStatus.ERROR or evaluation.error is None:
        raise KpiHistorianHistoryError('KPI error history requires an ERROR evaluation')
    return {
        'timestamp_utc': evaluation.watermark.timestamp_utc,
        'key': evaluation.key,
        'error': evaluation.error,
    }


def _check_current(check_current: Callable[[], None] | None) -> None:
    if check_current is not None:
        check_current()
