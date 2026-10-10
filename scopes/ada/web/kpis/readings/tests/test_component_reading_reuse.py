from __future__ import annotations

import pytest

from ada.web.kpis.readings import KpiLatestReadings, read_component_latest
from ada.web.ui.display_status import DisplayStatus


@pytest.mark.parametrize(
    'source, expected',
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': []}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.OK),
    ],
)
def test_read_component_latest_is_idempotent(source, expected):
    readings = read_component_latest(source)
    assert readings.source_status is expected
    assert read_component_latest(readings) is readings


def test_preconstructed_readings_are_reused_without_touching_values():
    values = {'some-key': object()}
    readings = KpiLatestReadings(values, DisplayStatus.OK)
    assert read_component_latest(readings) is readings
    assert readings.values is values
