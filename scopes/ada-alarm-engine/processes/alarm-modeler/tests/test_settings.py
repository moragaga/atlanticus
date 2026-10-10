from __future__ import annotations

import pytest

from ada.processes.alarm_modeler.settings import (
    _positive_float,
    _positive_int,
    configuration_specs,
)


def test_poll_and_rotation_use_independent_defaults():
    specs = {item.key: item for item in configuration_specs()}
    assert specs['ALARM_MODELER_POLL_SECONDS'].default == '1'
    assert specs['ALARM_MODELER_ROTATION_SECONDS'].default == '30'
    assert specs['ALARM_MODELER_MAX_VISIBLE_SLOTS'].default == '6'
    assert specs['ALARM_RUNTIME_APPLICATION'].required is True


def test_non_finite_or_non_positive_cadences_are_rejected():
    for value in ('0', '-1', 'nan', 'inf', '-inf', 'garbage'):
        with pytest.raises(ValueError):
            _positive_float(value, 'ALARM_MODELER_POLL_SECONDS')
    assert _positive_float('0.5', 'ALARM_MODELER_POLL_SECONDS') == 0.5


def test_slots_must_be_positive_integer():
    for value in ('0', '-1', '1.5', 'x'):
        with pytest.raises(ValueError):
            _positive_int(value, 'ALARM_MODELER_MAX_VISIBLE_SLOTS')
    assert _positive_int('6', 'ALARM_MODELER_MAX_VISIBLE_SLOTS') == 6
