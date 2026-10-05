import re
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaMaterializer,
    FabricaMetricDefinition,
    FabricaSourceBlob,
    FabricaStorageSource,
    FabricaStreamDefinition,
    FabricaValueKind,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


class _Source(FabricaStorageSource):
    def __init__(self, definition, tmp_path: Path):
        self.definition = definition
        self._tmp_path = tmp_path
        self.table = pa.Table.from_pydict(
            {
                'timestamp': ['2026-08-18T10:00:00Z'] * 3,
                'id_kpi': ['A', 'A', 'B'],
                'valor': ['10', '11', '999'],
                'nivel': ['DAY', '7LD', '7LD'],
                'timestamp_ejecucion': ['2026-08-18T10:01:00Z'] * 3,
                'particion': ['1'] * 3,
            }
        )

    def download(self, *, blob_name):
        path = self._tmp_path / 'download.parquet'
        path.write_bytes(b'placeholder')
        return str(path)

    def read_selected_columns(self, *, path, metric_ids):
        return self.table


def test_materializer_publishes_monthly_daily_and_unpartitioned_weekly(tmp_path) -> None:
    metric = FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT)
    definition = FabricaStreamDefinition(
        stream_key='kpis',
        source_prefix='kpi',
        source_filename_pattern=re.compile(r'kpi_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=(metric,),
                partition_dimensions=('year', 'month'),
            ),
            FabricaDatasetDefinition(
                name='weekly', source_value='7LD', route_segment='weekly', metrics=(metric,)
            ),
        ),
    )
    source = _Source(definition, tmp_path)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    materializer = FabricaMaterializer(source=source, runtime=runtime, definition=definition)
    blob = FabricaSourceBlob(
        name='kpi_20260818100000.parquet',
        source_file_timestamp_utc=datetime(2026, 8, 18, 10, tzinfo=UTC),
        size=1,
        etag='x',
        last_modified_utc=None,
    )
    result = materializer.materialize(source_blob=blob)
    assert result.source_row_count == 2
    assert tuple(item.partition_key for item in result.publications) == (
        'daily/year=2026/month=08',
        'weekly',
    )
    assert pq.read_table(
        tmp_path / 'datasets/fabrica/kpis/daily/year=2026/month=08/data.parquet'
    ).column_names == ['timestamp', 'a']
    assert pq.read_table(tmp_path / 'datasets/fabrica/kpis/weekly/data.parquet').column_names == [
        'timestamp',
        'a',
    ]


def test_monthly_daily_snapshot_is_partial_upsert(tmp_path) -> None:
    metrics = (
        FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT),
        FabricaMetricDefinition(id_kpi='B', metric_key='b', value_kind=FabricaValueKind.FLOAT),
    )
    definition = FabricaStreamDefinition(
        stream_key='kpis',
        source_prefix='kpi',
        source_filename_pattern=re.compile(r'kpi_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=metrics,
                partition_dimensions=('year', 'month'),
            ),
        ),
    )
    source = _Source(definition, tmp_path)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    materializer = FabricaMaterializer(source=source, runtime=runtime, definition=definition)

    source.table = pa.Table.from_pydict(
        {
            'timestamp': [
                '2026-08-31T10:00:00Z',
                '2026-09-01T10:00:00Z',
                '2026-09-01T10:00:00Z',
                '2026-09-02T10:00:00Z',
                '2026-09-02T10:00:00Z',
            ],
            'id_kpi': ['A', 'A', 'B', 'A', 'B'],
            'valor': ['8', '10', '20', '11', '21'],
            'nivel': ['DAY'] * 5,
            'timestamp_ejecucion': ['2026-09-02T11:00:00Z'] * 5,
            'particion': ['1'] * 5,
        }
    )
    first = FabricaSourceBlob(
        name='kpi_20260902110000.parquet',
        source_file_timestamp_utc=datetime(2026, 9, 2, 11, tzinfo=UTC),
        size=1,
        etag='first',
        last_modified_utc=None,
    )
    first_result = materializer.materialize(source_blob=first)
    assert tuple(item.partition_key for item in first_result.publications) == (
        'daily/year=2026/month=08',
        'daily/year=2026/month=09',
    )

    source.table = pa.Table.from_pydict(
        {
            'timestamp': [
                '2026-09-01T10:00:00Z',
                '2026-09-01T10:00:00Z',
                '2026-09-03T10:00:00Z',
            ],
            'id_kpi': ['A', 'B', 'A'],
            'valor': ['12', None, '13'],
            'nivel': ['DAY'] * 3,
            'timestamp_ejecucion': ['2026-09-03T11:00:00Z'] * 3,
            'particion': ['1'] * 3,
        }
    )
    second = FabricaSourceBlob(
        name='kpi_20260903110000.parquet',
        source_file_timestamp_utc=datetime(2026, 9, 3, 11, tzinfo=UTC),
        size=1,
        etag='second',
        last_modified_utc=None,
    )
    second_result = materializer.materialize(source_blob=second)
    assert tuple(item.partition_key for item in second_result.publications) == (
        'daily/year=2026/month=09',
    )

    august = pq.read_table(
        tmp_path / 'datasets/fabrica/kpis/daily/year=2026/month=08/data.parquet'
    ).to_pandas()
    september = pq.read_table(
        tmp_path / 'datasets/fabrica/kpis/daily/year=2026/month=09/data.parquet'
    ).to_pandas()

    assert august['a'].tolist() == [8.0]
    assert september['a'].tolist() == [12.0, 11.0, 13.0]
    assert september['b'].tolist()[:2] == [20.0, 21.0]
    assert september['b'].isna().tolist() == [False, False, True]
