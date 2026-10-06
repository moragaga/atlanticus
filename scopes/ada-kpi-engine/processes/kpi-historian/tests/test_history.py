from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.kpis.core import KpiStatus, KpiValueKind, KpiValueType
from ada.processes.kpi_historian.errors import KpiHistorianHistoryError
from ada.processes.kpi_historian.history import KpiHistorianMaterializer

from .support import batch, evaluation, watermark


class DatasetMerger:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def merge(self, **kwargs):
        self.calls.append(kwargs)
        return object()


def test_materializer_persists_scalar_contract_without_json_quoting() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    evaluations = (
        evaluation(
            'text-state',
            watermark_value=current,
            value='1',
            parsed_value='1',
            value_type=KpiValueType.TEXT,
        ),
        evaluation(
            'float-value',
            watermark_value=current,
            value='1234.29',
            parsed_value='1.234,29',
            value_type=KpiValueType.FLOAT,
        ),
    )
    result = materializer.materialize(batches=(batch(*evaluations),))
    assert result.history_rows == 2
    rows = {row['key']: row for row in runtime.calls[0]['data'].to_pylist()}
    assert rows['text-state']['value_type'] == 'text'
    assert rows['text-state']['value'] == '1'
    assert rows['text-state']['parsed_value'] == '1'
    assert rows['float-value']['value_type'] == 'float'
    assert rows['float-value']['value'] == '1234.29'
    assert rows['float-value']['parsed_value'] == '1.234,29'


def test_materializer_encodes_json_only_once_and_has_no_parsed_duplicate() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    value = {'b': 2, 'a': 1}
    result = materializer.materialize(
        batches=(
            batch(
                evaluation(
                    'json',
                    watermark_value=current,
                    value_kind=KpiValueKind.JSON,
                    value=value,
                )
            ),
        )
    )
    assert result.history_rows == 1
    row = runtime.calls[0]['data'].to_pylist()[0]
    assert row['value_kind'] == 'json'
    assert row['value_type'] is None
    assert row['value'] == '{"a":1,"b":2}'
    assert row['parsed_value'] is None


def test_materializer_routes_errors_even_without_history_flag() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    evaluations = (
        evaluation(
            'error-no-history',
            watermark_value=current,
            status=KpiStatus.ERROR,
            persist_history=False,
            error='CalculationError',
        ),
        evaluation(
            'ignored',
            watermark_value=current,
            persist_history=False,
        ),
    )
    result = materializer.materialize(batches=(batch(*evaluations),))
    assert result.history_rows == 0
    assert result.error_rows == 1
    assert result.error_publications == 1
    assert runtime.calls[0]['data'].to_pylist()[0] == {
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
        batches=(
            batch(
                evaluation(
                    'a',
                    watermark_value=current,
                    persist_history=False,
                )
            ),
        )
    )
    assert result.last_watermark_utc == current.to_text()
    assert result.history_rows == 0
    assert result.error_rows == 0
    assert runtime.calls == []


def test_materializer_distinguishes_degraded_json_from_explicit_empty_json() -> None:
    runtime = DatasetMerger()
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    result = materializer.materialize(
        batches=(
            batch(
                evaluation(
                    'missing-json',
                    watermark_value=current,
                    status=KpiStatus.MISSING,
                    value_kind=KpiValueKind.JSON,
                ),
                evaluation(
                    'error-json',
                    watermark_value=current,
                    status=KpiStatus.ERROR,
                    value_kind=KpiValueKind.JSON,
                    error='RuntimeError',
                ),
                evaluation(
                    'empty-json',
                    watermark_value=current,
                    value_kind=KpiValueKind.JSON,
                    value={'rows': []},
                ),
            ),
        )
    )
    assert result.history_rows == 3
    assert result.error_rows == 1
    rows = {row['key']: row for row in runtime.calls[0]['data'].to_pylist()}
    assert rows['missing-json']['status'] == 'missing'
    assert rows['missing-json']['value'] is None
    assert rows['error-json']['status'] == 'error'
    assert rows['error-json']['value'] is None
    assert rows['empty-json']['status'] == 'ok'
    assert rows['empty-json']['value'] == '{"rows":[]}'
    assert runtime.calls[1]['data'].to_pylist()[0]['error'] == 'RuntimeError'
