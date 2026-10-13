from __future__ import annotations

import pytest

from ada.web.application.generic.alarm_surface_binding import (
    attach_operational_alarm_surface,
)
from ada.web.application.generic.application import create_application_definition


def test_surface_registration_reads_exact_tool_store_and_keeps_empty_slots():
    definition = attach_operational_alarm_surface(create_application_definition(), tool_key='io')
    surface = next(module for module in definition.modules if module.name == 'ada-alarm-live-surface')
    registered = []

    class DashStub:
        def callback(self, *args):
            registered.extend(args)
            return lambda function: function

    surface.register_callbacks(DashStub(), None)
    assert registered[2].component_id == {'type': 'ada-alarm-live-store', 'tool': 'io'}


def test_denied_cards_leave_alarm_board_height_reserved():
    definition = attach_operational_alarm_surface(
        create_application_definition(), tool_key='io', can_view=lambda: False,
    )
    surface = next(module for module in definition.modules if module.name == 'ada-alarm-live-surface')
    registered = []

    class DashStub:
        def callback(self, *args):
            def register(function):
                registered.append(function)
                return function
            return register

    surface.register_callbacks(DashStub(), None)
    children, style = registered[0](None)
    assert children == []
    assert style == {'--ada-alarm-live-slot-count': '1'}


def test_duplicate_surface_is_rejected():
    definition = attach_operational_alarm_surface(create_application_definition(), tool_key='io')
    with pytest.raises(ValueError, match='already attached'):
        attach_operational_alarm_surface(definition, tool_key='io')
