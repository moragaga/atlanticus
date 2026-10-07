from datetime import UTC, datetime

from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY,
    AlarmConfiguration,
    AlarmConfigurationProjection,
    AlarmConfigurationSnapshot,
)
from ada.contracts.tools import ToolDependencyManifest
from ada.processes.alarm_materialization import AlarmMaterializationCandidate


def _projection() -> AlarmConfigurationProjection:
    return AlarmConfigurationProjection(
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        source_release_id='alarm-r7',
        source_published_at_utc=datetime(2026, 10, 7, 12, tzinfo=UTC),
        projected_at_utc=datetime(2026, 10, 7, 12, 1, tzinfo=UTC),
        snapshot=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r9',
                tools=(),
            ),
        ),
    )


def test_candidate_captures_stable_projection_evidence() -> None:
    projection = _projection()

    candidate = AlarmMaterializationCandidate.capture(projection)

    assert candidate.projection == projection
    assert candidate.source_key == ALARM_CONFIGURATION_SOURCE_KEY
    assert candidate.source_release_id == 'alarm-r7'
    assert candidate.alarm_configuration_revision == 'alarm-r7'
    assert candidate.confirmed_tool_catalog_revision == 'tools-r9'
    assert candidate.fingerprint == projection.fingerprint
