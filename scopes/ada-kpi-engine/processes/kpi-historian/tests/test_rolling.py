from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pyarrow as pa
import pytest

from ada.kpis.core import KpiStatus, KpiValueType, KpiWatermark
from ada.kpis.history import KpiHistorianAuthority, history_schema
from ada.kpis.history.rolling_dataset import (
    rolling_definition,
    rolling_state_from_table,
    rolling_target,
)
from ada.processes.kpi_historian.errors import KpiHistorianRollingError
from ada.processes.kpi_historian.rolling import KpiHistorianRollingMaterializer
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime, DatasetRuntimeWriteError
from tests.support import batch, evaluation, watermark


class HistoryRuntime:
    def __init__(self, rows_by_day=None) -> None:
        self.rows_by_day = {} if rows_by_day is None else rows_by_day
        self.calls = []

    def scan_table(self, **kwargs):
        self.calls.append(kwargs)
        partition = kwargs['targets'][0].partition.as_dict()
        day = f'{partition["year"]}-{partition["month"]}-{partition["day"]}'
        rows = self.rows_by_day.get(day, [])
        return SimpleNamespace(table=pa.Table.from_pylist(rows, schema=history_schema()))


class FailingRollingRuntime:
    def __init__(self, runtime: DatasetRuntime) -> None:
        self.runtime = runtime
        self.fail_replace = False

    def read_table(self, **kwargs):
        return self.runtime.read_table(**kwargs)

    def replace(self, **kwargs):
        if self.fail_replace:
            raise DatasetRuntimeWriteError('disk failure')
        return self.runtime.replace(**kwargs)


def _authority(value: KpiWatermark) -> KpiHistorianAuthority:
    return KpiHistorianAuthority(value.timestamp_utc)


def _materializer(tmp_path, *, history=None):
    rolling_runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))
    return (
        KpiHistorianRollingMaterializer(
            history_runtime=HistoryRuntime() if history is None else history,
            rolling_runtime=rolling_runtime,
            application_root=tmp_path,
        ),
        rolling_runtime,
    )


def _read(runtime: DatasetRuntime):
    result = runtime.read_table(
        definition=rolling_definition(),
        target=rolling_target(),
    )
    return rolling_state_from_table(result.table)


def test_incremental_materialization_writes_only_observed_physical_points(tmp_path) -> None:
    materializer, runtime = _materializer(tmp_path)
    first = watermark(0)
    second = watermark(1)

    materializer.materialize(
        batches=(
            batch(
                evaluation('a', watermark_value=first, value='1.0'),
                evaluation('b', watermark_value=first, status=KpiStatus.MISSING),
            ),
            batch(evaluation('a', watermark_value=second, value='2.0')),
        ),
        previous_authority=None,
        authority=_authority(second),
    )

    metadata, points = _read(runtime)
    assert points == {
        first.timestamp_utc: {'a': '1.0'},
        second.timestamp_utc: {'a': '2.0'},
    }
    assert dict(metadata.value_types) == {'a': 'float'}
    assert materializer.path == tmp_path / 'timeseries' / 'current.parquet'
    assert materializer.is_coherent(_authority(second)) is True


def test_empty_physical_coverage_is_a_confirmed_publication(tmp_path) -> None:
    materializer, runtime = _materializer(tmp_path)
    current = watermark(1)

    materializer.materialize(
        batches=(
            batch(
                evaluation(
                    'a',
                    watermark_value=current,
                    status=KpiStatus.MISSING,
                )
            ),
        ),
        previous_authority=None,
        authority=_authority(current),
    )

    metadata, points = _read(runtime)
    assert points == {}
    assert metadata.coverage_start_utc is None
    assert metadata.coverage_end_utc is None
    assert dict(metadata.value_types) == {}
    assert materializer.path.is_file()


def test_value_type_change_clears_previous_series(tmp_path) -> None:
    materializer, runtime = _materializer(tmp_path)
    first = watermark(0)
    second = watermark(1)

    materializer.materialize(
        batches=(
            batch(evaluation('a', watermark_value=first, value='1.0')),
            batch(
                evaluation(
                    'a',
                    watermark_value=second,
                    value='ready',
                    value_type=KpiValueType.TEXT,
                )
            ),
        ),
        previous_authority=None,
        authority=_authority(second),
    )

    metadata, points = _read(runtime)
    assert points == {second.timestamp_utc: {'a': 'ready'}}
    assert dict(metadata.value_types) == {'a': 'text'}


def test_rebuild_reads_durable_history(tmp_path) -> None:
    current = watermark(2)
    history = HistoryRuntime(
        {
            '2026-09-01': [
                {
                    'timestamp_utc': watermark(1).timestamp_utc,
                    'key': 'a',
                    'status': 'ok',
                    'value_kind': 'value',
                    'value_type': 'float',
                    'value': '1.0',
                    'parsed_value': '1,0',
                },
                {
                    'timestamp_utc': current.timestamp_utc,
                    'key': 'b',
                    'status': 'ok',
                    'value_kind': 'value',
                    'value_type': 'integer',
                    'value': '2',
                    'parsed_value': '2',
                },
            ]
        }
    )
    materializer, runtime = _materializer(tmp_path, history=history)

    materializer.rebuild(authority=_authority(current))

    metadata, points = _read(runtime)
    assert points == {
        watermark(1).timestamp_utc: {'a': '1.0'},
        current.timestamp_utc: {'b': '2'},
    }
    assert dict(metadata.value_types) == {'a': 'float', 'b': 'integer'}
    assert len(history.calls) == 2


def test_failed_dataset_replacement_preserves_last_committed_rolling(tmp_path) -> None:
    actual_runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))
    rolling_runtime = FailingRollingRuntime(actual_runtime)
    materializer = KpiHistorianRollingMaterializer(
        history_runtime=HistoryRuntime(),
        rolling_runtime=rolling_runtime,
        application_root=tmp_path,
    )
    first = watermark(1)
    second = watermark(2)
    materializer.materialize(
        batches=(batch(evaluation('a', watermark_value=first, value='1.0')),),
        previous_authority=None,
        authority=_authority(first),
    )
    committed = materializer.path.read_bytes()
    rolling_runtime.fail_replace = True

    with pytest.raises(KpiHistorianRollingError, match='publication failed'):
        materializer.materialize(
            batches=(batch(evaluation('a', watermark_value=second, value='2.0')),),
            previous_authority=_authority(first),
            authority=_authority(second),
        )

    assert materializer.path.read_bytes() == committed


def test_nonaligned_target_watermark_is_rejected(tmp_path) -> None:
    materializer, _ = _materializer(tmp_path)
    current = KpiWatermark(datetime(2026, 9, 1, 5, 0, 10, tzinfo=UTC))

    with pytest.raises(KpiHistorianRollingError, match='30-second grid'):
        materializer.materialize(
            batches=(batch(evaluation('a', watermark_value=current)),),
            previous_authority=None,
            authority=_authority(current),
        )
