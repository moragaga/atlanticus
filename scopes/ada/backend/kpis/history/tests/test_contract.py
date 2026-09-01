from datetime import date

import pyarrow as pa

from ada.kpis.history import (
    HISTORY_KEY_COLUMNS,
    HISTORY_MATERIALIZATION,
    HISTORY_ORDER_COLUMNS,
    HISTORY_PARTITION_DIMENSIONS,
    HISTORY_SCHEMA_VERSION,
    error_history_definition,
    error_history_schema,
    error_history_target,
    history_definition,
    history_schema,
    history_target,
)


def test_history_dataset_contract_is_canonical() -> None:
    definition = history_definition()
    target = history_target(date(2026, 9, 1))

    assert HISTORY_SCHEMA_VERSION == 1
    assert HISTORY_MATERIALIZATION == 'daily'
    assert HISTORY_PARTITION_DIMENSIONS == ('year', 'month', 'day')
    assert HISTORY_KEY_COLUMNS == ('timestamp_utc', 'key')
    assert HISTORY_ORDER_COLUMNS == ('timestamp_utc', 'key')
    assert definition.key.identifier == 'kpis/history'
    assert definition.resolve_route_segments(target) == (
        'kpis',
        'history',
        'year=2026',
        'month=09',
        'day=01',
    )


def test_error_history_dataset_contract_is_canonical() -> None:
    definition = error_history_definition()
    target = error_history_target(date(2026, 9, 1))

    assert definition.key.identifier == 'kpis/error-history'
    assert definition.resolve_route_segments(target) == (
        'kpis',
        'error-history',
        'year=2026',
        'month=09',
        'day=01',
    )


def test_history_schema_is_shared_and_explicit() -> None:
    schema = history_schema()

    assert schema.names == [
        'timestamp_utc',
        'key',
        'status',
        'value_kind',
        'value',
        'parsed_value',
    ]
    assert schema.field('timestamp_utc').type == pa.timestamp('us', tz='UTC')
    assert schema.field('timestamp_utc').nullable is False
    assert schema.field('key').nullable is False
    assert schema.field('status').nullable is False
    assert schema.field('value_kind').nullable is False
    assert schema.field('value').nullable is True
    assert schema.field('parsed_value').nullable is True


def test_error_history_schema_is_shared_and_explicit() -> None:
    schema = error_history_schema()

    assert schema.names == ['timestamp_utc', 'key', 'error']
    assert schema.field('timestamp_utc').type == pa.timestamp('us', tz='UTC')
    assert all(schema.field(name).nullable is False for name in schema.names)


def test_daily_target_rejects_datetime() -> None:
    from datetime import UTC, datetime

    try:
        history_target(datetime(2026, 9, 1, tzinfo=UTC))
    except TypeError as error:
        assert str(error) == 'day must be a date'
    else:
        raise AssertionError('datetime must not be accepted as a date partition')
