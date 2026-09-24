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
        self.table = pa.Table.from_pydict({
            'timestamp': ['2026-08-18T10:00:00Z'] * 3,
            'id_kpi': ['A', 'A', 'B'],
            'valor': ['10', '11', '999'],
            'nivel': ['DAY', '7LD', '7LD'],
            'timestamp_ejecucion': ['2026-08-18T10:01:00Z'] * 3,
            'particion': ['1'] * 3,
        })

    def download(self, *, blob_name):
        path = self._tmp_path / 'download.parquet'
        path.write_bytes(b'placeholder')
        return str(path)

    def read_selected_columns(self, *, path, metric_ids):
        return self.table


def test_materializer_publishes_only_requested_level_and_metrics(tmp_path) -> None:
    metric = FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT)
    definition = FabricaStreamDefinition(
        stream_key='kpis', source_prefix='kpi',
        source_filename_pattern=re.compile(r'kpi_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(
            FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=(metric,)),
            FabricaDatasetDefinition(name='weekly', source_value='7LD', route_segment='weekly', metrics=(metric,)),
        ),
    )
    source = _Source(definition, tmp_path)
    runtime = DatasetRuntime(store=ParquetDatasetStore(root=tmp_path / 'datasets'))
    materializer = FabricaMaterializer(source=source, runtime=runtime, definition=definition)
    blob = FabricaSourceBlob(
        name='kpi_20260818100000.parquet', source_file_timestamp_utc=datetime(2026, 8, 18, 10, tzinfo=UTC),
        size=1, etag='x', last_modified_utc=None,
    )
    result = materializer.materialize(source_blob=blob)
    assert result.source_row_count == 2
    assert tuple(item.partition_key for item in result.publications) == ('daily', 'weekly')
    assert pq.read_table(tmp_path / 'datasets/fabrica/kpis/daily/data.parquet').column_names == ['timestamp', 'a']
    assert pq.read_table(tmp_path / 'datasets/fabrica/kpis/weekly/data.parquet').column_names == ['timestamp', 'a']
