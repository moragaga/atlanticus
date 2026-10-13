from __future__ import annotations

import pytest

from ada.web.application.generic.alarm_surface_binding import (
    attach_operational_alarm_surface,
)
from ada.web.application.generic.application import create_application_definition


def _surface(*, can_view=None):
    definition = attach_operational_alarm_surface(
        create_application_definition(), tool_key='io', can_view=can_view,
    )
    return next(
        module for module in definition.modules if module.name == 'ada-alarm-live-surface'
    )


def _registered_callback(surface):
    dependencies = []
    callbacks = []

    class DashStub:
        def callback(self, *args):
            dependencies.extend(args)

            def register(function):
                callbacks.append(function)
                return function

            return register

    surface.register_callbacks(DashStub(), None)
    return dependencies, callbacks[0]


def _ready_store():
    return {
        'tool_key': 'io',
        'availability': 'ready',
        'live': {
            'tool_key': 'io',
            'schema_version': 2,
            'retired': False,
            'max_visible_slots': 6,
            'alarms': {
                'occ-1': {
                    'title': 'MP10',
                    'cause_text': 'Risk of MP10',
                    'kind': 'RISK',
                    'business_category': 'SAFETY_HEALTH',
                    'color': 'YELLOW',
                    'criticality': 'C3',
                },
            },
            'operator_view': [{'slot': 1, 'occurrence_id': 'occ-1'}],
        },
    }


def test_surface_registration_uses_store_timestamp_as_input_and_data_as_state():
    dependencies, _ = _registered_callback(_surface())
    assert [(dependency.component_id, dependency.component_property) for dependency in dependencies] == [
        ('ada-alarm-live-board', 'children'),
        ('ada-alarm-live-board', 'style'),
        ({'type': 'ada-alarm-live-store', 'tool': 'io'}, 'modified_timestamp'),
        ({'type': 'ada-alarm-live-store', 'tool': 'io'}, 'data'),
    ]
    assert type(dependencies[2]).__name__ == 'Input'
    assert type(dependencies[3]).__name__ == 'State'


@pytest.mark.parametrize('timestamp', [None, -1, 0, 1234])
def test_ready_store_renders_alarm_from_initial_and_updated_data(timestamp):
    _, callback = _registered_callback(_surface(can_view=lambda: True))
    children, style = callback(timestamp, _ready_store())
    assert len(children) == 1
    assert children[0].to_plotly_json()['props']['data-ada-alarm-occurrence-id'] == 'occ-1'
    assert style == {'--ada-alarm-live-slot-count': '6'}


def test_denied_cards_leave_alarm_board_height_reserved():
    _, callback = _registered_callback(_surface(can_view=lambda: False))
    children, style = callback(-1, _ready_store())
    assert children == []
    assert style == {'--ada-alarm-live-slot-count': '1'}


def test_empty_store_keeps_empty_board_with_default_capacity():
    _, callback = _registered_callback(_surface(can_view=lambda: True))
    children, style = callback(-1, None)
    assert children == []
    assert style == {'--ada-alarm-live-slot-count': '1'}


def test_duplicate_surface_is_rejected():
    definition = attach_operational_alarm_surface(create_application_definition(), tool_key='io')
    with pytest.raises(ValueError, match='already attached'):
        attach_operational_alarm_surface(definition, tool_key='io')
