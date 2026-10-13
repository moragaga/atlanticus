from datetime import UTC, datetime, timedelta, timezone

import pytest

from atlanticus.operational_data.core import DataInputContext


def test_data_input_context_accepts_absent_as_of_for_manually_built_context() -> None:
    assert DataInputContext({}).as_of is None


def test_data_input_context_normalizes_aware_as_of_to_utc() -> None:
    local = datetime(2026, 8, 20, 21, 2, tzinfo=timezone(timedelta(hours=-4)))

    context = DataInputContext({}, as_of=local)

    assert context.as_of == datetime(2026, 8, 21, 1, 2, tzinfo=UTC)


def test_data_input_context_rejects_naive_or_subsecond_as_of() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        DataInputContext({}, as_of=datetime(2026, 8, 20, 21, 2))

    with pytest.raises(ValueError, match='second precision'):
        DataInputContext({}, as_of=datetime(2026, 8, 20, 21, 2, 0, 1, tzinfo=UTC))
