from __future__ import annotations

import pytest

from ada.web.application.generic.alarm_surface_binding import (
    attach_operational_alarm_surface,
)
from ada.web.application.generic.application import create_application_definition


def _surface(*, can_view=None, component_keys=()):
    definition = attach_operational_alarm_surface(
        create_application_definition(), tool_key='io', can_view=can_view,
        component_keys=component_keys,
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


def test_surface_registration_uses_live_store_data_as_input():
    dependencies, _ = _registered_callback(_surface())
    assert [(dependency.component_id, dependency.component_property) for dependency in dependencies] == [
        ('ada-alarm-live-board', 'children'),
        ('ada-alarm-live-board', 'style'),
        ({'type': 'ada-alarm-live-store', 'tool': 'io'}, 'data'),
    ]
    assert type(dependencies[2]).__name__ == 'Input'


def test_ready_store_renders_alarm_from_initial_and_updated_data():
    _, callback = _registered_callback(_surface(can_view=lambda: True))
    children, style = callback(_ready_store())
    assert len(children) == 1
    assert children[0].to_plotly_json()['props']['data-ada-alarm-occurrence-id'] == 'occ-1'
    assert style == {'--ada-alarm-live-slot-count': '6'}


def test_two_integrated_alarms_from_updated_projection_render_in_their_slots():
    data = _ready_store()
    mine = data['live']['alarms']['occ-1']
    mine['visual_target'] = {
        'tool_key': 'io',
        'tool_kind': 'integrated_operations',
        'component_keys': ['cmp_general_mina', 'cmp_transporte'],
        'display_component_key': 'cmp_general_mina',
        'display_scope': 'mine',
        'subcomponents': [
            {'owner_component_key': 'cmp_general_mina', 'subcomponent_key': 'sub_mp10'},
            {'owner_component_key': 'cmp_transporte', 'subcomponent_key': 'sub_turno'},
        ],
    }
    data['live']['alarms']['occ-2'] = {
        'title': 'TK-050',
        'cause_text': 'Nivel fuera de rango',
        'kind': 'IMPACT',
        'business_category': 'PRODUCTIVITY',
        'color': 'RED',
        'criticality': 'C3',
        'visual_target': {
            'tool_key': 'io',
            'tool_kind': 'integrated_operations',
            'component_keys': ['cmp_flotacion'],
            'display_component_key': 'cmp_flotacion',
            'display_scope': 'plant',
            'subcomponents': [
                {'owner_component_key': 'cmp_flotacion', 'subcomponent_key': 'sub_selectiva'},
            ],
        },
    }
    data['live']['operator_view'].append({'slot': 4, 'occurrence_id': 'occ-2'})
    _, callback = _registered_callback(_surface(can_view=lambda: True))
    children, style = callback(data)
    props = [item.to_plotly_json()['props'] for item in children]
    assert [(item['data-ada-alarm-occurrence-id'], item['style']['gridColumn']) for item in props] == [
        ('occ-1', '1'), ('occ-2', '4'),
    ]
    assert [item['data-ada-alarm-display-scope'] for item in props] == ['mine', 'plant']
    assert [item['data-ada-alarm-color'] for item in props] == ['YELLOW', 'RED']
    assert style == {'--ada-alarm-live-slot-count': '6'}


def test_integrated_overview_uses_tool_component_order_before_browser_animation():
    data = _ready_store()
    mine = 'cmp_general_mina_6df268db211b'
    flotation = 'cmp_flotacion_9bbf64c07ea7'
    data['live']['alarms']['occ-1']['visual_target'] = {
        'tool_key': 'io', 'tool_kind': 'integrated_operations',
        'component_keys': [mine], 'display_component_key': mine, 'display_scope': 'mine',
    }
    data['live']['alarms']['occ-2'] = {
        'title': 'TK-050', 'color': 'RED',
        'visual_target': {
            'tool_key': 'io', 'tool_kind': 'integrated_operations',
            'component_keys': [flotation], 'display_component_key': flotation,
            'display_scope': 'plant',
        },
    }
    data['live']['operator_view'].append({'slot': 4, 'occurrence_id': 'occ-2'})
    components = (mine, 'carguio', 'transporte', 'chancado', 'stockpile', 'molienda',
                  flotation, 'fluidos', 'puerto')
    _, callback = _registered_callback(_surface(component_keys=components))
    children, style = callback(data)
    assert [card.style['gridColumn'] for card in children] == ['1', '7']
    assert [card.to_plotly_json()['props']['data-ada-alarm-slot']
            for card in children] == ['1', '4']
    assert style == {'--ada-alarm-live-slot-count': '6'}


def test_denied_cards_leave_alarm_board_height_reserved():
    _, callback = _registered_callback(_surface(can_view=lambda: False))
    children, style = callback(_ready_store())
    assert children == []
    assert style == {'--ada-alarm-live-slot-count': '1'}


def test_empty_store_keeps_empty_board_with_default_capacity():
    _, callback = _registered_callback(_surface(can_view=lambda: True))
    children, style = callback(None)
    assert children == []
    assert style == {'--ada-alarm-live-slot-count': '1'}


def test_duplicate_surface_is_rejected():
    definition = attach_operational_alarm_surface(create_application_definition(), tool_key='io')
    with pytest.raises(ValueError, match='already attached'):
        attach_operational_alarm_surface(definition, tool_key='io')
