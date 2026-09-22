import pytest

from ada_command_center.alarms.materialization import RuntimeAlarmConfiguration

from .support import identity, plan, resolution_key


def test_runtime_configuration_distinguishes_defined_disabled_and_executable() -> None:
    active = plan()
    disabled = identity('disabled')
    configuration = RuntimeAlarmConfiguration(
        resolution_key=resolution_key(),
        defined_alarm_identities=(active.identity, disabled),
        planned_alarms=(active,),
        parameters_by_alarm={active.identity: {'limit': 10.0}},
    )
    assert disabled in configuration.defined_alarm_identities
    assert tuple(alarm.identity for alarm in configuration.planned_alarms) == (active.identity,)
    assert disabled not in configuration.parameters_by_alarm


def test_runtime_configuration_rejects_plan_outside_defined_identities() -> None:
    active = plan()
    with pytest.raises(ValueError, match='must be defined'):
        RuntimeAlarmConfiguration(
            resolution_key=resolution_key(),
            defined_alarm_identities=(identity('other'),),
            planned_alarms=(active,),
            parameters_by_alarm={},
        )


def test_runtime_configuration_rejects_plan_with_different_resolution_provenance() -> None:
    active = plan()
    with pytest.raises(ValueError, match='configuration revision'):
        RuntimeAlarmConfiguration(
            resolution_key=resolution_key(alarm_revision='R43'),
            defined_alarm_identities=(active.identity,),
            planned_alarms=(active,),
            parameters_by_alarm={},
        )
    with pytest.raises(ValueError, match='tool revision'):
        RuntimeAlarmConfiguration(
            resolution_key=resolution_key(tool_revision='T19'),
            defined_alarm_identities=(active.identity,),
            planned_alarms=(active,),
            parameters_by_alarm={},
        )


def test_runtime_configuration_rejects_parameters_for_non_executable_alarm() -> None:
    active = plan()
    disabled = identity('disabled')
    with pytest.raises(ValueError, match='planned alarms'):
        RuntimeAlarmConfiguration(
            resolution_key=resolution_key(),
            defined_alarm_identities=(active.identity, disabled),
            planned_alarms=(active,),
            parameters_by_alarm={disabled: {'limit': 10.0}},
        )


def test_runtime_configuration_accepts_only_static_parameter_values() -> None:
    active = plan()
    with pytest.raises(TypeError, match='TEXT, FLOAT, or BOOLEAN'):
        RuntimeAlarmConfiguration(
            resolution_key=resolution_key(),
            defined_alarm_identities=(active.identity,),
            planned_alarms=(active,),
            parameters_by_alarm={active.identity: {'count': 2}},
        )
