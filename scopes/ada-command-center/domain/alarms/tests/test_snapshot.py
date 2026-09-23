import pytest

from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
    AlarmConfigurationValidationError,
)


def test_alarm_configuration_snapshot_round_trips_configuration_and_tool_revision() -> None:
    value = AlarmConfigurationSnapshot(
        configuration=AlarmConfiguration(rules=(), messages=()),
        confirmed_tool_catalog_revision='tools-r2',
    )

    restored = AlarmConfigurationSnapshot.from_document(value.to_document())

    assert restored == value
    assert restored.confirmed_tool_catalog_revision == 'tools-r2'


def test_alarm_configuration_snapshot_rejects_missing_tool_revision() -> None:
    with pytest.raises(AlarmConfigurationValidationError):
        AlarmConfigurationSnapshot.from_document({'configuration': {'rules': [], 'messages': []}})
