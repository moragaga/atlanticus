from __future__ import annotations

import pytest
from dash import dcc, no_update

from ada_command_center.web.alarms.configuration.web.authoring import (
    add_rule,
    add_visual_target,
    empty_authoring_document,
    set_rule_field,
    set_visual_components,
    set_visual_target_field,
    synchronize_visual_targets,
)
from ada_command_center.web.alarms.configuration.web.callbacks import (
    register_alarm_configuration_admin_callbacks,
)
from ada_command_center.web.alarms.configuration.web.ids import TARGET_FIELD_TYPE
from ada_command_center.web.alarms.configuration.web.layout import _visual_targets_editor

from .test_workspace_hydration import CallbackAppStub, _context

REFERENCES = {
    'tools': [
        {
            'tool_key': 'integrated_tool',
            'kind': 'integrated_operations',
            'display_name': 'Operaciones Integradas',
            'components': [
                {
                    'component_key': 'general_mina',
                    'display_name': 'General Mina',
                    'subcomponents': [],
                },
                {'component_key': 'chancado', 'display_name': 'Chancado', 'subcomponents': []},
            ],
        },
        {
            'tool_key': 'process_tool',
            'kind': 'process',
            'display_name': 'Proceso',
            'components': [
                {'component_key': 'main', 'display_name': 'Main', 'subcomponents': []},
            ],
        },
    ],
}


def _target(document):
    return document['rules'][0]['visual_targets'][0]


def _make_document(tool_key='integrated_tool'):
    document = add_visual_target(add_rule(empty_authoring_document()), 0)
    return set_visual_target_field(document, 0, 0, 'tool_key', tool_key)


def _descendants(node):
    if isinstance(node, (tuple, list)):
        for item in node:
            yield from _descendants(item)
        return
    if node is None:
        return
    yield node
    yield from _descendants(getattr(node, 'children', None))


def test_integrated_location_is_a_selected_affected_component():
    document = _make_document()
    document = set_visual_components(document, 0, 0, ['general_mina', 'chancado'], REFERENCES)
    document = set_visual_target_field(document, 0, 0, 'display_component_key', 'general_mina')
    assert _target(document)['component_keys'] == ['general_mina', 'chancado']
    assert _target(document)['display_component_key'] == 'general_mina'
    with pytest.raises(ValueError, match='selected components'):
        set_visual_target_field(document, 0, 0, 'display_component_key', 'foreign_component')


def test_removing_affected_component_clears_location_not_others():
    document = _make_document()
    document = set_visual_components(document, 0, 0, ['general_mina', 'chancado'], REFERENCES)
    document = set_visual_target_field(document, 0, 0, 'display_component_key', 'general_mina')
    result = set_visual_components(document, 0, 0, ['chancado'], REFERENCES)
    assert _target(result)['component_keys'] == ['chancado']
    assert _target(result)['display_component_key'] is None
    assert _target(document)['display_component_key'] == 'general_mina'


def test_tool_change_clears_location_and_process_does_not_keep_manual_location():
    document = _make_document()
    document = set_visual_components(document, 0, 0, ['general_mina'], REFERENCES)
    document = set_visual_target_field(document, 0, 0, 'display_component_key', 'general_mina')
    changed = set_visual_target_field(document, 0, 0, 'tool_key', 'process_tool')
    assert _target(changed)['component_keys'] == []
    assert _target(changed)['display_component_key'] is None
    changed = set_rule_field(changed, 0, 'escalation.origin_tool_key', 'process_tool')
    synchronized = synchronize_visual_targets(changed, 0, REFERENCES)
    assert _target(synchronized)['display_component_key'] is None


def test_integrated_selector_options_follow_selected_components():
    value = {
        'tool_key': 'integrated_tool',
        'component_keys': ['general_mina'],
        'display_component_key': 'general_mina',
        'subcomponents': [],
        'process_projection_mode': None,
    }
    editor = _visual_targets_editor(0, [value], REFERENCES)
    fields = [
        component
        for component in _descendants(editor)
        if isinstance(component, dcc.Dropdown)
        and isinstance(getattr(component, 'id', None), dict)
        and component.id.get('type') == TARGET_FIELD_TYPE
        and component.id.get('field') == 'display_component_key'
    ]
    assert len(fields) == 1
    assert fields[0].value == 'general_mina'
    assert [item['value'] for item in fields[0].options] == ['general_mina']
    value['tool_key'] = 'process_tool'
    assert not [
        component
        for component in _descendants(_visual_targets_editor(0, [value], REFERENCES))
        if isinstance(component, dcc.Dropdown)
        and isinstance(getattr(component, 'id', None), dict)
        and component.id.get('field') == 'display_component_key'
    ]


def test_live_selector_preserves_or_clears_position_with_component_choices():
    app = CallbackAppStub()
    context, _binding = _context()
    register_alarm_configuration_admin_callbacks(app, context)
    callback = app.callbacks['update_display_component_choices']
    options, selected, disabled = callback(
        ['general_mina'], 'integrated_tool', REFERENCES, 'general_mina'
    )
    assert [option['value'] for option in options] == ['general_mina']
    assert selected == 'general_mina'
    assert disabled is False
    options, selected, disabled = callback(
        ['chancado'], 'integrated_tool', REFERENCES, 'general_mina'
    )
    assert [option['value'] for option in options] == ['chancado']
    assert selected is None
    assert disabled is False
    options, selected, disabled = callback([], 'integrated_tool', REFERENCES, 'general_mina')
    assert (options, selected, disabled) == ([], None, True)
    assert callback([], 'integrated_tool', None, None) == (no_update, no_update, no_update)


def test_typing_does_not_rebuild_listing_behind_open_modal():
    app = CallbackAppStub()
    context, _binding = _context()
    register_alarm_configuration_admin_callbacks(app, context)
    callback = app.callbacks['render_listings']
    document = _make_document()
    assert callback(document, REFERENCES, {'rule_index': 0}) == (no_update, no_update)
    assert callback(document, REFERENCES, {'message_index': 0}) == (no_update, no_update)
    closed = callback(document, REFERENCES, {'page': 'families', 'rule_index': None})
    assert closed != (no_update, no_update)
