import pytest

from ada.processes.alarm_runtime.errors import AlarmRuntimeConfigurationError
from ada.processes.alarm_runtime.settings import _positive_float, configuration_specs


def test_configuration_specs_include_administrative_execution_barrier() -> None:
    specs = {spec.key: spec for spec in configuration_specs()}
    assert specs['ATLANTICUS_JOB_EXECUTION_DISABLED'].default == 'false'
    assert specs['ALARM_RUNTIME_POLL_SECONDS'].default == '5'


def test_poll_interval_must_be_positive() -> None:
    assert _positive_float('2.5', 'ALARM_RUNTIME_POLL_SECONDS') == 2.5
    with pytest.raises(AlarmRuntimeConfigurationError):
        _positive_float('0', 'ALARM_RUNTIME_POLL_SECONDS')
