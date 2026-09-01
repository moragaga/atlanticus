from datetime import UTC, datetime

from ada.configuration.tools_lifecycle import (
    ToolConfigurationProjectionSnapshot,
    ToolConfigurationSourceSnapshot,
    build_tool_configuration_digest,
)

from .helpers import valid_configuration


def test_source_snapshot_round_trip_preserves_configuration() -> None:
    configuration = valid_configuration()
    snapshot = ToolConfigurationSourceSnapshot.create(
        configuration=configuration,
        saved_by='manager-user',
        saved_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )

    restored = ToolConfigurationSourceSnapshot.from_document(snapshot.to_document())

    assert restored == snapshot
    assert restored.revision == build_tool_configuration_digest(configuration)


def test_projection_snapshot_round_trip_preserves_source_revision() -> None:
    source = ToolConfigurationSourceSnapshot.create(
        configuration=valid_configuration(),
        saved_by='manager-user',
        saved_at_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    projection = ToolConfigurationProjectionSnapshot.create(
        configuration=source.configuration,
        source_revision=source.revision,
        projected_by='projector',
        projected_at_utc=datetime(2026, 9, 1, 12, 5, tzinfo=UTC),
    )

    restored = ToolConfigurationProjectionSnapshot.from_document(projection.to_document())

    assert restored == projection
    assert restored.source_revision == source.revision
