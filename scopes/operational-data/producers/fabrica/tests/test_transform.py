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
        stream_key='kpis',
        source_prefix='kpis',
        source_filename_pattern=re.compile(r'kpi_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(
            FabricaDatasetDefinition(
                name='daily', source_value='DAY', route_segment='daily', metrics=(metric,)
            ),
            FabricaDatasetDefinition(
                name='weekly', source_value='7LD', route_segment='weekly', metrics=(metric,)
            ),
        ),
    )


def test_output_filters_exact_dataset_metric_pairs_and_pivots() -> None:
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-08-10T10:00:00Z'] * 3,
            'id_kpi': ['A', 'A', 'A'],
            'valor': ['91', '90', '999'],
            'nivel': ['DAY', '7LD', 'HOUR'],
            'timestamp_ejecucion': ['2026-08-10T11:00:00Z'] * 3,
            'particion': ['202608'] * 3,
        }
    )
    result = build_partition_frames(table=table, definition=_definition())
    assert result.source_row_count == 2
    assert result.frames['daily'].loc[0, 'a'] == 91.0
    assert result.frames['weekly'].loc[0, 'a'] == 90.0
    assert str(result.frames['daily']['a'].dtype) == 'Float64'
    assert result.unknown_source_values == ('HOUR',)


def test_merge_does_not_replace_previous_value_with_null() -> None:
    metric = FabricaMetricDefinition(id_kpi='A', metric_key='a', value_kind=FabricaValueKind.FLOAT)
    current = pd.DataFrame(
        {
            'timestamp': pd.to_datetime(['2026-08-10T10:00:00Z'], utc=True),
            'a': pd.Series([91.0], dtype='Float64'),
        }
    )
    incoming = pd.DataFrame(
        {
            'timestamp': pd.to_datetime(['2026-08-10T10:00:00Z'], utc=True),
            'a': pd.Series([pd.NA], dtype='Float64'),
        }
    )
    merged = merge_partition_frame(current=current, incoming=incoming, metrics=(metric,))
    assert merged.loc[0, 'a'] == 91.0


def test_daily_and_weekly_share_deduplication_ordering() -> None:
    metric = FabricaMetricDefinition(
        id_kpi='A',
        metric_key='a',
        value_kind=FabricaValueKind.FLOAT,
    )
    definition = FabricaStreamDefinition(
        stream_key='planes',
        source_prefix='planes',
        source_filename_pattern=re.compile(r'planes_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=(metric,),
                partition_dimensions=('year', 'month'),
            ),
            FabricaDatasetDefinition(
                name='weekly',
                source_value='7LDB',
                route_segment='weekly',
                metrics=(metric,),
                partition_dimensions=('year', 'month'),
            ),
        ),
    )
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-08-10T10:00:00Z'] * 4,
            'id_kpi': ['A'] * 4,
            'valor': ['10', '11', '20', '21'],
            'nivel': ['DAY', 'DAY', '7LDB', '7LDB'],
            'timestamp_ejecucion': [
                '2026-08-10T10:01:00Z',
                '2026-08-10T10:02:00Z',
                '2026-08-10T10:01:00Z',
                '2026-08-10T10:02:00Z',
            ],
            'particion': ['1', '2', '1', '2'],
        }
    )

    result = build_partition_frames(table=table, definition=definition)

    assert result.frames['daily']['a'].tolist() == [11.0]
    assert result.frames['weekly']['a'].tolist() == [21.0]


def test_source_mismatch_identifies_only_affected_kpi_with_synthetic_data() -> None:
    metrics = tuple(
        FabricaMetricDefinition(
            id_kpi=f'TEST_KPI_{letter}',
            metric_key=f'test_kpi_{letter.lower()}',
            value_kind=FabricaValueKind.FLOAT,
        )
        for letter in ('A', 'B', 'C')
    )
    definition = FabricaStreamDefinition(
        stream_key='test-stream',
        source_prefix='test',
        source_filename_pattern=re.compile(r'test_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='test',
        datasets=(
            FabricaDatasetDefinition(
                name='daily', source_value='DAY', route_segment='daily', metrics=metrics
            ),
        ),
    )
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-10-08T00:00:00Z'] * 5,
            'id_kpi': ['TEST_KPI_A', 'TEST_KPI_A', 'TEST_KPI_B', 'TEST_KPI_B', 'OTHER'],
            'valor': ['1', '2', '3', '4', '5'],
            'nivel': ['MTD', 'YTD', 'DAY', 'MTD', 'OTHER_LEVEL'],
            'timestamp_ejecucion': ['2026-10-08T00:00:01Z'] * 5,
            'particion': ['1'] * 5,
        }
    )

    result = build_partition_frames(table=table, definition=definition)

    assert result.source_mismatches == (
        ('TEST_KPI_A', 'test_kpi_a', 'daily', 'DAY', ('MTD', 'YTD')),
    )
    assert result.missing_source_kpis == (('TEST_KPI_C', 'test_kpi_c', ('DAY',)),)
    assert result.unknown_source_values == ('MTD', 'YTD')
    assert result.frames['daily']['test_kpi_b'].tolist() == [3.0]
    assert result.frames['daily']['test_kpi_a'].isna().all()


def test_missing_expected_source_can_be_globally_known() -> None:
    metric = FabricaMetricDefinition(
        id_kpi='TEST_KPI_A', metric_key='test_kpi_a', value_kind=FabricaValueKind.FLOAT
    )
    definition = FabricaStreamDefinition(
        stream_key='test-stream',
        source_prefix='test',
        source_filename_pattern=re.compile(r'test_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='test',
        datasets=(
            FabricaDatasetDefinition(
                name='daily', source_value='DAY', route_segment='daily', metrics=(metric,)
            ),
            FabricaDatasetDefinition(
                name='weekly', source_value='7LDB', route_segment='weekly', metrics=(metric,)
            ),
        ),
    )
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-10-08T00:00:00Z'],
            'id_kpi': ['TEST_KPI_A'],
            'valor': ['1'],
            'nivel': ['DAY'],
            'timestamp_ejecucion': ['2026-10-08T00:00:01Z'],
            'particion': ['1'],
        }
    )

    result = build_partition_frames(table=table, definition=definition)

    assert result.unknown_source_values == ()
    assert result.source_mismatches == (
        ('TEST_KPI_A', 'test_kpi_a', 'weekly', '7LDB', ('DAY',)),
    )


def test_extra_sources_do_not_cause_mismatches_when_expected_are_present() -> None:
    metric_a, metric_b, metric_c = tuple(
        FabricaMetricDefinition(
            id_kpi=f'TEST_KPI_{letter}',
            metric_key=f'test_kpi_{letter.lower()}',
            value_kind=FabricaValueKind.FLOAT,
        )
        for letter in ('A', 'B', 'C')
    )
    definition = FabricaStreamDefinition(
        stream_key='test-stream',
        source_prefix='test',
        source_filename_pattern=re.compile(r'test_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='test',
        datasets=(
            FabricaDatasetDefinition(
                name='daily',
                source_value='DAY',
                route_segment='daily',
                metrics=(metric_a, metric_b, metric_c),
            ),
            FabricaDatasetDefinition(
                name='weekly',
                source_value='7LDB',
                route_segment='weekly',
                metrics=(metric_a,),
            ),
        ),
    )
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-10-08T00:00:00Z'] * 7,
            'id_kpi': [
                'TEST_KPI_A', 'TEST_KPI_A', 'TEST_KPI_A',
                'TEST_KPI_B', 'TEST_KPI_B', 'TEST_KPI_B', 'OTHER',
            ],
            'valor': ['1', '2', '3', '4', '5', '6', '7'],
            'nivel': ['DAY', '7LDB', 'MTD', 'DAY', '7LDB', 'YTD', 'OTHER_LEVEL'],
            'timestamp_ejecucion': ['2026-10-08T00:00:01Z'] * 7,
            'particion': ['1'] * 7,
        }
    )

    result = build_partition_frames(table=table, definition=definition)

    assert result.source_mismatches == ()
    assert result.unknown_source_values == ('MTD', 'YTD')
    assert result.source_row_count == 3
    assert result.frames['daily'].loc[0, 'test_kpi_a'] == 1.0
    assert result.frames['daily'].loc[0, 'test_kpi_b'] == 4.0
    assert result.frames['weekly'].loc[0, 'test_kpi_a'] == 2.0
    assert result.missing_source_kpis == (('TEST_KPI_C', 'test_kpi_c', ('DAY',)),)


def test_missing_kpi_in_multiple_datasets_generates_one_diagnostic() -> None:
    present = FabricaMetricDefinition(
        id_kpi='TEST_PRESENT', metric_key='test_present', value_kind=FabricaValueKind.FLOAT
    )
    missing = FabricaMetricDefinition(
        id_kpi='TEST_KEY', metric_key='test_key', value_kind=FabricaValueKind.FLOAT
    )
    definition = FabricaStreamDefinition(
        stream_key='test-stream',
        source_prefix='test',
        source_filename_pattern=re.compile(r'test_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='test',
        datasets=(
            FabricaDatasetDefinition(
                name='daily', source_value='DAY', route_segment='daily', metrics=(present, missing)
            ),
            FabricaDatasetDefinition(
                name='weekly', source_value='7LDB', route_segment='weekly', metrics=(missing,)
            ),
        ),
    )
    table = pa.Table.from_pydict(
        {
            'timestamp': ['2026-10-08T00:00:00Z'],
            'id_kpi': ['TEST_PRESENT'],
            'valor': ['123'],
            'nivel': ['DAY'],
            'timestamp_ejecucion': ['2026-10-08T00:00:01Z'],
            'particion': ['1'],
        }
    )

    result = build_partition_frames(table=table, definition=definition)

    assert result.source_mismatches == ()
    assert result.missing_source_kpis == (('TEST_KEY', 'test_key', ('DAY', '7LDB')),)
    assert result.frames['daily'].loc[0, 'test_present'] == 123.0
    assert result.source_row_count == 1
