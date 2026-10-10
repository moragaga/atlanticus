import pytest

from ada.processes.alarm_runtime.errors import AlarmRuntimeConfigurationError
from ada.processes.alarm_runtime.settings import (
    _pi_source,
    _positive_float,
    configuration_specs,
)
from atlanticus.operational_data.sources import PiSourceProvider


def test_configuration_specs_include_runtime_and_operational_data_routes() -> None:
    specs = {spec.key: spec for spec in configuration_specs()}
    assert specs['ATLANTICUS_JOB_EXECUTION_DISABLED'].default == 'false'
    assert specs['ALARM_RUNTIME_POLL_SECONDS'].default == '1'
    assert specs['PI_SOURCE'].required is True
    assert specs['PI_APPLICATION'].required is True
    assert specs['DISPATCH_APPLICATION'].required is False
    assert specs['BLOCKGRADE_APPLICATION'].required is False
    assert specs['REMANENTES_APPLICATION'].required is False
    assert specs['FABRICA_PLANES_APPLICATION'].required is False
    assert specs['FABRICA_KPIS_APPLICATION'].required is False
    assert specs['METEODATA_APPLICATION'].required is False


def test_pi_source_uses_the_shared_operational_data_provider_contract() -> None:
    assert _pi_source('NOTPII') is PiSourceProvider.NOTPII
    assert _pi_source('PI_WEB_API') is PiSourceProvider.PI_WEB_API
    with pytest.raises(AlarmRuntimeConfigurationError):
        _pi_source('unknown')


def test_poll_interval_must_be_positive() -> None:
    assert _positive_float('2.5', 'ALARM_RUNTIME_POLL_SECONDS') == 2.5
    with pytest.raises(AlarmRuntimeConfigurationError):
        _positive_float('0', 'ALARM_RUNTIME_POLL_SECONDS')
