from __future__ import annotations

from ada.kpis.history import (
    decode_history_value,
    error_history_definition,
    error_history_target,
    history_definition,
    history_target,
)
from ada.processes.kpi_historian.history import KpiHistorianMaterializer
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime
from tests.support import batch, evaluation, watermark


def test_materialization_is_idempotent_on_real_dataset_runtime(tmp_path) -> None:
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    current_batch = batch(evaluation('produccion_total', watermark_value=current, value=42.5))

    first = materializer.materialize(batches=(current_batch,))
    second = materializer.materialize(batches=(current_batch,))

    target = history_target(current.timestamp_utc.date())
    table = runtime.read_table(definition=history_definition(), target=target).table
    rows = table.to_pylist()
    assert first.history_publications == 1
    assert second.history_publications == 1
    assert len(rows) == 1
    assert rows[0]['key'] == 'produccion_total'
    assert decode_history_value(rows[0]['value']) == 42.5


def test_error_history_uses_shared_error_contract(tmp_path) -> None:
    from ada.kpis.core import KpiStatus

    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    materializer = KpiHistorianMaterializer(runtime=runtime)
    current = watermark()
    current_batch = batch(
        evaluation(
            'fallido',
            watermark_value=current,
            status=KpiStatus.ERROR,
            persist_history=False,
            error='CalculationError',
        )
    )

    materializer.materialize(batches=(current_batch,))

    target = error_history_target(current.timestamp_utc.date())
    table = runtime.read_table(definition=error_history_definition(), target=target).table
    assert table.to_pylist() == [
        {
            'timestamp_utc': current.timestamp_utc,
            'key': 'fallido',
            'error': 'CalculationError',
        }
    ]
