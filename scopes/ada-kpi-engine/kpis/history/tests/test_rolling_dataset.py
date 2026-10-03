from datetime import UTC, datetime

from ada.kpis.history import KpiRollingMetadata, historian_revision
from ada.kpis.history.rolling_dataset import (
    rolling_definition,
    rolling_state_from_table,
    rolling_table,
    rolling_target,
)
from atlanticus.datasets import SingleArtifactLayout


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
