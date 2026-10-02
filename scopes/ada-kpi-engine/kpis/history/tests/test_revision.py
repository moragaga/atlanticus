from datetime import UTC, datetime, timedelta, timezone

import pytest

from ada.kpis.history import (
    KpiHistoryContractError,
    historian_revision,
    historian_watermark_text,
)


def test_historian_revision_is_deterministic_for_same_authority() -> None:
    value = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    first = historian_revision(watermark_utc=value)
    second = historian_revision(watermark_utc=value)

    assert first == second
    assert len(first) == 64
    assert set(first) <= set('0123456789abcdef')


def test_historian_revision_normalizes_same_instant_to_utc() -> None:
    chile_like = timezone(-timedelta(hours=4))
    local_value = datetime(2026, 9, 1, 8, 0, tzinfo=chile_like)
    utc_value = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    assert historian_watermark_text(local_value) == '2026-09-01T12:00:00Z'
    assert historian_revision(watermark_utc=local_value) == historian_revision(
        watermark_utc=utc_value
    )


def test_new_committed_watermark_changes_historian_revision() -> None:
    first = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    second = datetime(2026, 9, 1, 12, 0, 1, tzinfo=UTC)

    assert historian_revision(watermark_utc=first) != historian_revision(watermark_utc=second)


def test_historian_watermark_requires_aware_whole_seconds() -> None:
    with pytest.raises(KpiHistoryContractError, match='timezone-aware'):
        historian_revision(watermark_utc=datetime(2026, 9, 1, 12, 0))
    with pytest.raises(KpiHistoryContractError, match='whole seconds'):
        historian_revision(watermark_utc=datetime(2026, 9, 1, 12, 0, 0, 1, tzinfo=UTC))
