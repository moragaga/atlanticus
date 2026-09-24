import re
from datetime import UTC, datetime

from atlanticus.data_producers.fabrica import (
    FabricaDatasetDefinition,
    FabricaStreamDefinition,
    parse_source_file_timestamp,
)


def _definition() -> FabricaStreamDefinition:
    return FabricaStreamDefinition(
        stream_key='kpis', source_prefix='MLP/kpi',
        source_filename_pattern=re.compile(r'kpi_fabrica_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='kpis',
        datasets=(FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=()),),
    )


def test_file_timestamp_is_parsed_with_declared_file_timezone() -> None:
    assert parse_source_file_timestamp(
        definition=_definition(), blob_name='kpi_fabrica_20260810173031.parquet',
    ) == datetime(2026, 8, 10, 17, 30, 31, tzinfo=UTC)


def test_source_path_selects_local_chilean_calendar_day() -> None:
    definition = _definition()
    assert definition.source_day_prefix(datetime(2026, 8, 11, 1, 0, tzinfo=UTC)) == (
        'MLP/kpi/year=2026/month=08/day=10/'
    )


def test_local_file_timestamp_can_be_normalized_when_provider_is_confirmed() -> None:
    definition = FabricaStreamDefinition(
        stream_key='planes', source_prefix='planes',
        source_filename_pattern=re.compile(r'planes_(?P<file_timestamp>\d{14})\.parquet$'),
        output_route_segment='planes',
        datasets=(FabricaDatasetDefinition(name='daily', source_value='DAY', route_segment='daily', metrics=()),),
        source_file_timezone_name='America/Santiago',
    )
    assert parse_source_file_timestamp(
        definition=definition, blob_name='planes_20260924150000.parquet',
    ) == datetime(2026, 9, 24, 18, tzinfo=UTC)
