from datetime import UTC, datetime

import pyarrow as pa

from ada.kpis.history import KpiRollingMetadata, historian_revision
from ada.kpis.history.dataset import (
    error_history_schema,
    error_history_table,
    history_records_from_table,
    history_schema,
    history_table,
    rolling_definition,
    rolling_metadata_from_schema,
    rolling_projection_from_table,
    rolling_schema_token,
    rolling_state_from_table,
    rolling_table,
    rolling_table_schema_token,
    rolling_target,
)
from atlanticus.datasets import SingleArtifactLayout


def test_durable_schemas_are_explicit() -> None:
    schema = history_schema()
    assert schema.names == [
        'timestamp_utc',
        'key',
        'status',
        'value_kind',
        'value_type',
        'value',
        'parsed_value',
    ]
    assert schema.field('timestamp_utc').type == pa.timestamp('us', tz='UTC')
    assert schema.field('timestamp_utc').nullable is False
    assert schema.field('key').nullable is False
    assert schema.field('status').nullable is False
    assert schema.field('value_kind').nullable is False
    assert schema.field('value_type').nullable is True
    assert schema.field('value').nullable is True
    assert schema.field('parsed_value').nullable is True

    error_schema = error_history_schema()
    assert error_schema.names == ['timestamp_utc', 'key', 'error']
    assert error_schema.field('timestamp_utc').type == pa.timestamp('us', tz='UTC')
    assert all(error_schema.field(name).nullable is False for name in error_schema.names)


def test_durable_table_helpers_round_trip_projection() -> None:
    timestamp = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
    table = history_table(
        (
            {
                'timestamp_utc': timestamp,
                'key': 'a',
                'status': 'ok',
                'value_kind': 'value',
                'value_type': 'integer',
                'value': '1',
                'parsed_value': '1',
            },
        )
    )
    projection = table.select(
        ['timestamp_utc', 'key', 'status', 'value_kind', 'value_type', 'value']
    )

    assert history_records_from_table(projection) == (
        {
            'timestamp_utc': timestamp,
            'key': 'a',
            'status': 'ok',
            'value_kind': 'value',
            'value_type': 'integer',
            'value': '1',
        },
    )

    errors = error_history_table(
        ({'timestamp_utc': timestamp, 'key': 'b', 'error': 'CalculationError'},)
    )
    assert errors.schema.equals(error_history_schema(), check_metadata=True)


def test_rolling_dataset_preserves_named_empty_single_artifact_contract() -> None:
    definition = rolling_definition()
    target = rolling_target()
    layout = definition.get_materialization(target.materialization).layout

    assert isinstance(layout, SingleArtifactLayout)
    assert layout.artifact_name == 'current'
    assert layout.allow_empty is True
    assert definition.resolve_route_segments(target) == ('timeseries',)


def test_rolling_table_round_trip_preserves_metadata_and_points() -> None:
    watermark = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
    metadata = KpiRollingMetadata(
        watermark_utc=watermark,
        historian_revision=historian_revision(watermark_utc=watermark),
        coverage_start_utc=watermark,
        coverage_end_utc=watermark,
        value_types={'a': 'integer'},
    )

    table = rolling_table(metadata=metadata, points={watermark: {'a': '1'}})
    restored_metadata, points = rolling_state_from_table(table)

    assert restored_metadata == metadata
    assert points == {watermark: {'a': '1'}}
    assert rolling_schema_token(table.schema) == rolling_table_schema_token(table)


def test_projected_rolling_uses_authoritative_metadata_separately() -> None:
    watermark = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
    metadata = KpiRollingMetadata(
        watermark_utc=watermark,
        historian_revision=historian_revision(watermark_utc=watermark),
        coverage_start_utc=watermark,
        coverage_end_utc=watermark,
        value_types={'a': 'integer', 'b': 'integer'},
    )
    table = rolling_table(
        metadata=metadata,
        points={watermark: {'a': '1', 'b': '2'}},
    )
    authoritative = rolling_metadata_from_schema(table.schema)
    projected = table.select(['timestamp_utc', 'b'])

    values = rolling_projection_from_table(
        projected,
        metadata=authoritative,
        keys=('b',),
    )

    assert values == {'b': {watermark: '2'}}
