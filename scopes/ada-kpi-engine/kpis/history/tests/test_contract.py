from datetime import date

from ada.kpis.history import (
    HISTORY_KEY_COLUMNS,
    HISTORY_MATERIALIZATION,
    HISTORY_ORDER_COLUMNS,
    HISTORY_PARTITION_DIMENSIONS,
    HISTORY_SCHEMA_VERSION,
    error_history_definition,
    error_history_target,
    history_definition,
    history_target,
)


def test_history_dataset_contract_is_canonical() -> None:
    definition = history_definition()
    target = history_target(date(2026, 9, 1))
    assert HISTORY_SCHEMA_VERSION == 2
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
