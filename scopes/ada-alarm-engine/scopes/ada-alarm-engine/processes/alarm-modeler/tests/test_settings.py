from __future__ import annotations

import pytest

from ada.processes.alarm_modeler.settings import (
    AlarmModelerSettings,
    _positive_float,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(*, application: str, runtime_application: str) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': application,
        'VOLUMEN_PATH': '/tmp/atlanticus',
        'ALARM_RUNTIME_APPLICATION': runtime_application,
        'ALARM_MODELER_POLL_SECONDS': '1',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_poll_is_an_operational_setting_not_a_visual_rotation_policy():
    specs = {item.key: item for item in configuration_specs()}
    assert specs['ALARM_MODELER_POLL_SECONDS'].default == '1'
    assert specs['ALARM_RUNTIME_APPLICATION'].required is True
    assert 'ALARM_MODELER_ROTATION_SECONDS' not in specs
    assert 'ALARM_MODELER_MAX_VISIBLE_SLOTS' not in specs


@pytest.mark.parametrize(
    ('application', 'runtime_application'),
    [
        ('ada-alarm-engine-local', 'ada-alarm-engine-local'),
        ('ada-alarm-modeler-local', 'ada-alarm-engine-local'),
    ],
)
def test_runtime_application_can_be_shared_or_separate(application, runtime_application):
    settings = AlarmModelerSettings.from_configuration(
        _configuration(application=application, runtime_application=runtime_application)
    )

    assert settings.runtime_application == runtime_application


def test_non_finite_or_non_positive_poll_intervals_are_rejected():
    for value in ('0', '-1', 'nan', 'inf', '-inf', 'garbage'):
        with pytest.raises(ValueError):
            _positive_float(value, 'ALARM_MODELER_POLL_SECONDS')
    assert _positive_float('0.5', 'ALARM_MODELER_POLL_SECONDS') == 0.5
