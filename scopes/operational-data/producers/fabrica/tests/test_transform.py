import re

import pandas as pd
import pyarrow as pa

from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    FabricaStreamDefinition,
    FabricaValueKind,
    build_partition_frames,
    merge_partition_frame,
)


def _definition():
    metric = FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT)
    return FabricaStreamDefinition(
        stream_key='kpis', source_prefix='kpis',
        source_filename_pattern=re.compile(r'kpi_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(
            FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=(metric,)),
            FabricaDatasetDefinition(name='weekly', source_value='7LD', route_segment='weekly', metrics=(metric,)),
        ),
    )


def test_output_filters_exact_dataset_metric_pairs_and_pivots() -> None:
    table = pa.Table.from_pydict({
        'timestamp': ['2026-08-10T10:00:00Z'] * 3,
        'id_kpi': ['A', 'A', 'A'], 'valor': ['91', '90', '999'],
        'nivel': ['DAY', '7LD', 'HOUR'],
        'timestamp_ejecucion': ['2026-08-10T11:00:00Z'] * 3,
        'particion': ['202608'] * 3,
    })
    result = build_partition_frames(table=table, definition=_definition())
    assert result.source_row_count == 2
    assert result.frames['daily'].loc[0, 'a'] == 91.0
    assert result.frames['weekly'].loc[0, 'a'] == 90.0
    assert str(result.frames['daily']['a'].dtype) == 'Float64'
    assert result.unknown_source_values == ()


def test_merge_does_not_replace_previous_value_with_null() -> None:
    metric = FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT)
    current = pd.DataFrame({'timestamp': pd.to_datetime(['2026-08-10T10:00:00Z'], utc=True), 'a': pd.Series([91.0], dtype='Float64')})
    incoming = pd.DataFrame({'timestamp': pd.to_datetime(['2026-08-10T10:00:00Z'], utc=True), 'a': pd.Series([pd.NA], dtype='Float64')})
    merged = merge_partition_frame(current=current, incoming=incoming, metrics=(metric,))
    assert merged.loc[0, 'a'] == 91.0
