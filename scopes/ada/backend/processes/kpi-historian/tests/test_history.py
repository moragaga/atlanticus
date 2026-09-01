from __future__ import annotations

from datetime import UTC, datetime

import pyarrow as pa
import pytest

from ada.kpis.core import KpiStatus
from ada.processes.kpi_historian.errors import KpiHistorianHistoryError
from ada.processes.kpi_historian.history import KpiHistorianMaterializer
from tests.support import batch, evaluation, watermark


class DatasetMerger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def merge(self, **kwargs):
        self.calls.append(kwargs)
        return object()


def test_materializer_routes_history_and_errors_without_duplicate_contracts() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    evaluations = (
        evaluation('ok', watermark_value=current, value=12.5, parsed_value=12.5),
        evaluation(
            'error-no-history',
            watermark_value=current,
            status=KpiStatus.ERROR,
            persist_history=False,
            error='CalculationError',
        ),
        evaluation('ignored', watermark_value=current, persist_history=False),
    )

    result = materializer.materialize(batches=(batch(*evaluations),))

    assert result.batches_processed == 1
    assert result.evaluations_processed == 3
    assert result.history_rows == 1
    assert result.error_rows == 1
    assert result.history_publications == 1
    assert result.error_publications == 1
    assert len(runtime.calls) == 2
    history_table = runtime.calls[0]['data']
    error_table = runtime.calls[1]['data']
    assert isinstance(history_table, pa.Table)
    assert history_table.to_pylist()[0]['key'] == 'ok'
    assert history_table.to_pylist()[0]['value'] == '12.5'
    assert error_table.to_pylist()[0] == {
        'timestamp_utc': current.timestamp_utc,
        'key': 'error-no-history',
        'error': 'CalculationError',
    }


def test_materializer_flushes_daily_partitions() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    first = watermark()
    second = type(first)(datetime(2026, 9, 2, 5, 0, tzinfo=UTC))

    result = materializer.materialize(
        batches=(
            batch(evaluation('a', watermark_value=first)),
            batch(evaluation('a', watermark_value=second)),
        )
    )

    assert result.history_publications == 2
    assert len(runtime.calls) == 2
    assert runtime.calls[0]['target'].partition.as_dict()['day'] == '01'
    assert runtime.calls[1]['target'].partition.as_dict()['day'] == '02'


def test_materializer_rejects_non_increasing_batches() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    current_batch = batch(evaluation('a', watermark_value=current))

    with pytest.raises(KpiHistorianHistoryError, match='strictly ordered'):
        materializer.materialize(batches=(current_batch, current_batch))


def test_materializer_can_advance_without_historical_rows() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()

    result = materializer.materialize(
        batches=(batch(evaluation('a', watermark_value=current, persist_history=False)),)
    )

    assert result.last_watermark_utc == current.to_text()
    assert result.history_rows == 0
    assert result.error_rows == 0
    assert runtime.calls == []
