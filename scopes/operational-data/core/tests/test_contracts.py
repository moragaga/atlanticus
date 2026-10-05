from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    ShiftScope,
    ShiftSelection,
    TimeWindow,
    TimeWindowUnit,
)


def test_time_window_keeps_fixed_delta_semantics_and_calendar_months() -> None:
    assert TimeWindow(30, TimeWindowUnit.MINUTES).to_timedelta() == timedelta(minutes=30)
    assert TimeWindow(2, TimeWindowUnit.HOURS).to_timedelta() == timedelta(hours=2)
    assert TimeWindow(3, TimeWindowUnit.DAYS).to_timedelta() == timedelta(days=3)

    monthly = TimeWindow(1, TimeWindowUnit.MONTHS)
    with pytest.raises(ValueError, match='no fixed timedelta'):
        monthly.to_timedelta()
    assert monthly.start_from(datetime(2026, 3, 31, 12, tzinfo=UTC)) == datetime(
        2026, 2, 28, 12, tzinfo=UTC
    )


def test_time_window_requires_typed_unit() -> None:
    with pytest.raises(TypeError, match='TimeWindowUnit'):
        TimeWindow(2, 'hours')  # type: ignore[arg-type]


def test_shift_scopes_preserve_dispatch_contract() -> None:
    assert ShiftSelection(ShiftScope.CURRENT).days is None
    assert ShiftSelection(ShiftScope.PREVIOUS).days is None
    assert ShiftSelection(ShiftScope.CURRENT_TURN).days is None
    assert ShiftSelection(ShiftScope.PREVIOUS_TURN).days is None
    assert ShiftSelection(ShiftScope.CURRENT_WEEK).days is None


def test_days_shift_scope_is_parameterized_from_one_to_seven() -> None:
    assert ShiftSelection(ShiftScope.DAYS, days=1).days == 1
    assert ShiftSelection(ShiftScope.DAYS, days=7).days == 7

    with pytest.raises(ValueError, match='requires an integer days value'):
        ShiftSelection(ShiftScope.DAYS)
    with pytest.raises(ValueError, match='between 1 and 7'):
        ShiftSelection(ShiftScope.DAYS, days=8)
    with pytest.raises(ValueError, match='only be declared'):
        ShiftSelection(ShiftScope.CURRENT, days=1)


def test_data_column_requires_explicit_canonical_type() -> None:
    assert DataColumn(' tag_a ', DataColumnType.FLOAT) == DataColumn('tag_a', DataColumnType.FLOAT)
    with pytest.raises(TypeError, match='DataColumnType'):
        DataColumn('tag_a', 'float')  # type: ignore[arg-type]
    with pytest.raises(ValueError, match='non-empty'):
        DataColumn(' ', DataColumnType.TEXT)


def test_data_column_types_cover_current_operational_schema_contract() -> None:
    assert {item.value for item in DataColumnType} == {
        'text',
        'integer',
        'float',
        'boolean',
        'date',
        'datetime',
    }
