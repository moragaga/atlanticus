from datetime import UTC, datetime

from ada.kpis.history import KpiRollingMetadata, historian_revision
from ada.kpis.history.rolling_dataset import (
    rolling_projection_from_table,
    rolling_table,
)


def test_projected_rolling_table_uses_authoritative_metadata_separately() -> None:
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
    ).select(['timestamp_utc', 'b'])

    projected = rolling_projection_from_table(
        table,
        metadata=metadata,
        keys=('b',),
    )

    assert projected == {'b': {watermark: '2'}}
