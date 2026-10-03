from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ada.kpis.core import KpiStatus, KpiValueType, KpiWatermark
from ada.kpis.history import KpiHistorianAuthority, KpiRollingMetadata, history_schema
from ada.processes.kpi_historian.errors import KpiHistorianRollingError
from ada.processes.kpi_historian.rolling import (
    KpiHistorianRollingMaterializer,
    rolling_path,
)
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


def _authority(value: KpiWatermark) -> KpiHistorianAuthority:
    return KpiHistorianAuthority(value.timestamp_utc)


def _read(path):
    table = pq.read_table(path)
    metadata = KpiRollingMetadata.from_bytes(table.schema.metadata[b'ada_kpi_timeseries'])
    return table, metadata


def test_rolling_path_is_a_direct_historian_application_child(tmp_path) -> None:
    assert rolling_path(tmp_path) == tmp_path / 'timeseries' / 'current.parquet'


def test_incremental_materialization_writes_only_observed_physical_points(tmp_path) -> None:
    runtime = HistoryRuntime()
    path = rolling_path(tmp_path)
    materializer = KpiHistorianRollingMaterializer(runtime=runtime, path=path)
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

    table, metadata = _read(path)
    assert runtime.calls == []
    assert table.column_names == ['timestamp_utc', 'a']
    assert table.to_pylist() == [
        {'timestamp_utc': first.timestamp_utc, 'a': '1.0'},
        {'timestamp_utc': second.timestamp_utc, 'a': '2.0'},
    ]
    assert metadata.coverage_start_utc == first.timestamp_utc
    assert metadata.coverage_end_utc == second.timestamp_utc
    assert dict(metadata.value_types) == {'a': 'float'}
    assert materializer.is_coherent(_authority(second)) is True


def test_empty_physical_coverage_writes_only_timestamp_schema_and_metadata(tmp_path) -> None:
    current = watermark(1)
    materializer = KpiHistorianRollingMaterializer(
        runtime=HistoryRuntime(),
        path=rolling_path(tmp_path),
    )

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

    table, metadata = _read(materializer.path)
    assert table.column_names == ['timestamp_utc']
    assert table.num_rows == 0
    assert metadata.coverage_start_utc is None
    assert metadata.coverage_end_utc is None
    assert dict(metadata.value_types) == {}
    assert materializer.is_coherent(_authority(current)) is True


def test_value_type_change_starts_a_new_logical_series_inside_the_rolling(tmp_path) -> None:
    materializer = KpiHistorianRollingMaterializer(
        runtime=HistoryRuntime(),
        path=rolling_path(tmp_path),
    )
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

    table, metadata = _read(materializer.path)
    assert table.to_pylist() == [
        {'timestamp_utc': second.timestamp_utc, 'a': 'ready'},
    ]
    assert dict(metadata.value_types) == {'a': 'text'}


def test_materialization_trims_points_at_or_before_24_hour_cutoff(tmp_path) -> None:
    materializer = KpiHistorianRollingMaterializer(
        runtime=HistoryRuntime(),
        path=rolling_path(tmp_path),
    )
    old = KpiWatermark(datetime(2026, 8, 31, 5, 0, tzinfo=UTC))
    current = KpiWatermark(datetime(2026, 9, 1, 5, 0, tzinfo=UTC))

    materializer.materialize(
        batches=(
            batch(evaluation('a', watermark_value=old, value='1.0')),
            batch(evaluation('a', watermark_value=current, value='2.0')),
        ),
        previous_authority=None,
        authority=_authority(current),
    )

    table, metadata = _read(materializer.path)
    assert table.to_pylist() == [
        {'timestamp_utc': current.timestamp_utc, 'a': '2.0'},
    ]
    assert metadata.coverage_start_utc == current.timestamp_utc


def test_rebuild_reads_durable_history_and_keeps_wide_shape(tmp_path) -> None:
    current = watermark(2)
    runtime = HistoryRuntime(
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
    materializer = KpiHistorianRollingMaterializer(runtime=runtime, path=rolling_path(tmp_path))

    materializer.rebuild(authority=_authority(current))

    table, metadata = _read(materializer.path)
    assert table.column_names == ['timestamp_utc', 'a', 'b']
    assert table.to_pylist() == [
        {'timestamp_utc': watermark(1).timestamp_utc, 'a': '1.0', 'b': None},
        {'timestamp_utc': current.timestamp_utc, 'a': None, 'b': '2'},
    ]
    assert dict(metadata.value_types) == {'a': 'float', 'b': 'integer'}
    assert len(runtime.calls) == 2


def test_corrupt_rolling_is_rebuilt_from_durable_history_when_previous_authority_exists(
    tmp_path,
) -> None:
    before = watermark(1)
    current = watermark(2)
    path = rolling_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not parquet')
    runtime = HistoryRuntime(
        {
            '2026-09-01': [
                {
                    'timestamp_utc': current.timestamp_utc,
                    'key': 'a',
                    'status': 'ok',
                    'value_kind': 'value',
                    'value_type': 'float',
                    'value': '2.0',
                    'parsed_value': '2,0',
                }
            ]
        }
    )
    materializer = KpiHistorianRollingMaterializer(runtime=runtime, path=path)

    materializer.materialize(
        batches=(batch(evaluation('a', watermark_value=current, value='2.0')),),
        previous_authority=_authority(before),
        authority=_authority(current),
    )

    table, metadata = _read(path)
    assert table.to_pylist() == [
        {'timestamp_utc': current.timestamp_utc, 'a': '2.0'},
    ]
    assert metadata.watermark_utc == current.timestamp_utc
    assert runtime.calls


def test_nonaligned_target_watermark_is_rejected(tmp_path) -> None:
    current = watermark(0, second=10)
    materializer = KpiHistorianRollingMaterializer(
        runtime=HistoryRuntime(),
        path=rolling_path(tmp_path),
    )

    with pytest.raises(KpiHistorianRollingError, match='30-second grid'):
        materializer.materialize(
            batches=(batch(evaluation('a', watermark_value=current)),),
            previous_authority=None,
            authority=_authority(current),
        )


def test_failed_replacement_preserves_last_committed_rolling(tmp_path, monkeypatch) -> None:
    path = rolling_path(tmp_path)
    materializer = KpiHistorianRollingMaterializer(runtime=HistoryRuntime(), path=path)
    first = watermark(1)
    second = watermark(2)
    materializer.materialize(
        batches=(batch(evaluation('a', watermark_value=first, value='1.0')),),
        previous_authority=None,
        authority=_authority(first),
    )
    committed_bytes = path.read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError('disk failure')

    monkeypatch.setattr('ada.processes.kpi_historian.rolling.pq.write_table', fail_write)

    with pytest.raises(KpiHistorianRollingError, match='atomic write failed'):
        materializer.materialize(
            batches=(batch(evaluation('a', watermark_value=second, value='2.0')),),
            previous_authority=_authority(first),
            authority=_authority(second),
        )

    assert path.read_bytes() == committed_bytes
