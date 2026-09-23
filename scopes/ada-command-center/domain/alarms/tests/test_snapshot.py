import pytest

from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
    AlarmConfigurationValidationError,
)
from ada_command_center.domain.tools import ToolDependencyManifest


def _manifest(revision: str = 'tools-r2') -> ToolDependencyManifest:
    return ToolDependencyManifest(
        confirmed_tool_catalog_revision=revision,
        tools=(),
    )


def test_alarm_configuration_snapshot_round_trips_configuration_and_tool_manifest() -> None:
    value = AlarmConfigurationSnapshot(
        configuration=AlarmConfiguration(rules=(), messages=()),
        tool_dependencies=_manifest(),
    )

    restored = AlarmConfigurationSnapshot.from_document(value.to_document())

    assert restored == value
    assert restored.confirmed_tool_catalog_revision == 'tools-r2'
    assert restored.tool_dependencies == _manifest()


def test_alarm_configuration_snapshot_rejects_missing_tool_manifest() -> None:
    with pytest.raises(AlarmConfigurationValidationError):
        AlarmConfigurationSnapshot.from_document({'configuration': {'rules': [], 'messages': []}})
