from __future__ import annotations

from datetime import UTC, datetime

import pyarrow as pa
import pytest

from atlanticus.datasets.parquet import (
    ColumnFilter,
    FilterOperator,
    ParquetDatasetStore,
    ParquetSchemaError,
)


def _target(definition, day):
    return definition.resolve_target(
        materialization='granular',
        partition={'year': '2026', 'month': '07', 'day': day},
    )


def _data(kind, *, time='2026-07-21T10:00:00+00:00'):
    timestamp = datetime.fromisoformat(time)
    return pa.table({
        'timestamp': pa.array([timestamp], type=pa.timestamp(kind, tz='UTC')),
        'value': pa.array([12.5], type=pa.float64()),
    })


@pytest.mark.parametrize(('physical', 'requested'), (('us', 'ns'), ('ns', 'us')))
def test_timestamp_projection_accepts_lossless_utc_precision(
    tmp_path, clock, pi_definition, physical, requested
):
    store = ParquetDatasetStore(root=tmp_path / 'store', clock=lambda: clock)
    target = _target(pi_definition, '21')
    store.replace(definition=pi_definition, target=target, table=_data(physical))
    schema = pa.schema([
        pa.field('timestamp', pa.timestamp(requested, tz='UTC')),
        pa.field('value', pa.float64()),
    ])

    result = store.scan(
        definition=pi_definition,
        targets=(target,),
        projection_schema=schema,
        filters=(ColumnFilter(
            column='timestamp',
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=datetime(2026, 7, 21, 9, tzinfo=UTC),
        ),),
    )
    assert result.table.schema.equals(schema)
    assert result.table['value'].to_pylist() == [12.5]
    assert store.read_schema(definition=pi_definition, target=target).field('timestamp').type == pa.timestamp(physical, tz='UTC')


def test_mixed_timestamp_precisions_scan_with_time_filter(tmp_path, clock, pi_definition):
    store = ParquetDatasetStore(root=tmp_path / 'store', clock=lambda: clock)
    first, second = _target(pi_definition, '20'), _target(pi_definition, '21')
    store.replace(definition=pi_definition, target=first, table=_data('ns', time='2026-07-20T10:00:00+00:00'))
    store.replace(definition=pi_definition, target=second, table=_data('us'))
    schema = pa.schema([
        pa.field('timestamp', pa.timestamp('us', tz='UTC')),
        pa.field('value', pa.float64()),
    ])
    result = store.scan(
        definition=pi_definition,
        targets=(first, second),
        projection_schema=schema,
        filters=(ColumnFilter(
            column='timestamp',
            operator=FilterOperator.GREATER_THAN_OR_EQUAL,
            value=datetime(2026, 7, 20, 0, tzinfo=UTC),
        ),),
    )
    assert result.table.schema.equals(schema)
    assert result.table.num_rows == 2


def test_submicrosecond_data_cannot_be_silently_truncated(tmp_path, clock, pi_definition):
    store = ParquetDatasetStore(root=tmp_path / 'store', clock=lambda: clock)
    target = _target(pi_definition, '21')
    midnight_ns = int(datetime(2026, 7, 21, tzinfo=UTC).timestamp()) * 1_000_000_000
    store.replace(
        definition=pi_definition,
        target=target,
        table=pa.table({'timestamp': pa.array(
            [midnight_ns + 1], type=pa.timestamp('ns', tz='UTC')
        )}),
    )
    with pytest.raises(ParquetSchemaError, match='without data loss'):
        store.scan(
            definition=pi_definition,
            targets=(target,),
            projection_schema=pa.schema([pa.field('timestamp', pa.timestamp('us', tz='UTC'))]),
        )


def test_mismatched_timezone_remains_invalid(tmp_path, clock, pi_definition):
    store = ParquetDatasetStore(root=tmp_path / 'store', clock=lambda: clock)
    target = _target(pi_definition, '21')
    store.replace(
        definition=pi_definition,
        target=target,
        table=pa.table({'timestamp': pa.array(
            [datetime(2026, 7, 21, 10, tzinfo=UTC)],
            type=pa.timestamp('ns', tz='America/Santiago'),
        )}),
    )
    with pytest.raises(ParquetSchemaError, match='incompatible type for projected column timestamp'):
        store.scan(
            definition=pi_definition,
            targets=(target,),
            projection_schema=pa.schema([pa.field('timestamp', pa.timestamp('us', tz='UTC'))]),
        )


def test_unrelated_type_remains_invalid(tmp_path, clock, pi_definition):
    store = ParquetDatasetStore(root=tmp_path / 'store', clock=lambda: clock)
    target = _target(pi_definition, '21')
    store.replace(definition=pi_definition, target=target, table=pa.table({'timestamp': pa.array([12.5])}))
    with pytest.raises(ParquetSchemaError, match='incompatible type for projected column timestamp'):
        store.scan(
            definition=pi_definition,
            targets=(target,),
            projection_schema=pa.schema([pa.field('timestamp', pa.timestamp('us', tz='UTC'))]),
        )
