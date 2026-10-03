from datetime import UTC, datetime

import pytest

from ada.kpis.history import (
    ROLLING_DIRECTORY,
    ROLLING_FILENAME,
    ROLLING_GRID_SECONDS,
    ROLLING_MAX_HOURS,
    ROLLING_METADATA_KEY,
    ROLLING_SCHEMA_VERSION,
    ROLLING_TIMESTAMP_COLUMN,
    KpiHistoryContractError,
    KpiRollingMetadata,
    historian_revision,
)


def _metadata(*, second: int = 0) -> KpiRollingMetadata:
    watermark = datetime(2026, 9, 1, 5, 0, second, tzinfo=UTC)
    return KpiRollingMetadata(
        watermark_utc=watermark,
        historian_revision=historian_revision(watermark_utc=watermark),
        coverage_start_utc=watermark,
        coverage_end_utc=watermark,
        value_types={'kpi-a': 'float'},
    )


def test_rolling_contract_is_fixed_and_compact() -> None:
    assert ROLLING_SCHEMA_VERSION == 1
    assert ROLLING_GRID_SECONDS == 30
    assert ROLLING_MAX_HOURS == 24
    assert ROLLING_DIRECTORY == 'timeseries'
    assert ROLLING_FILENAME == 'current.parquet'
    assert ROLLING_METADATA_KEY == 'ada_kpi_timeseries'
    assert ROLLING_TIMESTAMP_COLUMN == 'timestamp_utc'


def test_rolling_metadata_round_trip_is_canonical() -> None:
    metadata = _metadata()

    restored = KpiRollingMetadata.from_bytes(metadata.to_bytes())

    assert restored == metadata
    assert restored.to_payload()['value_types'] == {'kpi-a': 'float'}


def test_rolling_metadata_allows_empty_physical_coverage() -> None:
    watermark = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)

    metadata = KpiRollingMetadata(
        watermark_utc=watermark,
        historian_revision=historian_revision(watermark_utc=watermark),
        coverage_start_utc=None,
        coverage_end_utc=None,
        value_types={},
    )

    assert metadata.coverage_start_utc is None
    assert metadata.value_types == {}


def test_rolling_metadata_requires_30_second_alignment() -> None:
    with pytest.raises(KpiHistoryContractError, match='30-second grid'):
        _metadata(second=10)


def test_rolling_metadata_rejects_revision_mismatch() -> None:
    watermark = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)

    with pytest.raises(KpiHistoryContractError, match='historian_revision'):
        KpiRollingMetadata(
            watermark_utc=watermark,
            historian_revision='invalid',
            coverage_start_utc=None,
            coverage_end_utc=None,
            value_types={},
        )
