from __future__ import annotations

import pytest

from ada.processes.alarm_modeler.settings import _positive_float, configuration_specs


def test_poll_is_an_operational_setting_not_a_visual_rotation_policy():
    specs = {item.key: item for item in configuration_specs()}
    assert specs['ALARM_MODELER_POLL_SECONDS'].default == '1'
    assert specs['ALARM_RUNTIME_APPLICATION'].required is True
    assert 'ALARM_MODELER_ROTATION_SECONDS' not in specs
    assert 'ALARM_MODELER_MAX_VISIBLE_SLOTS' not in specs


def test_non_finite_or_non_positive_poll_intervals_are_rejected():
    for value in ('0', '-1', 'nan', 'inf', '-inf', 'garbage'):
        with pytest.raises(ValueError):
            _positive_float(value, 'ALARM_MODELER_POLL_SECONDS')
    assert _positive_float('0.5', 'ALARM_MODELER_POLL_SECONDS') == 0.5
