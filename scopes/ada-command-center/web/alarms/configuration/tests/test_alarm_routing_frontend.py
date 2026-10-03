from types import SimpleNamespace

from dash import dcc

from ada.contracts.tools.enums import ToolConfigurationKind
from ada_command_center.web.alarms.configuration.web.authoring import (
    routing_target_suggestions,
    synchronize_visual_targets,
    tool_reference_catalog_to_document,
    tool_suggestions,
)
from ada_command_center.web.alarms.configuration.web.layout import _escalation_editor

REFERENCES = {
    'catalog_revision': 'catalog-1',
    'routing_tools': [
        {'tool_key': 'p', 'display_name': 'Process', 'kind': 'process'},
        {'tool_key': 'p2', 'display_name': 'Other process', 'kind': 'process'},
        {'tool_key': 'io', 'display_name': 'Integrated', 'kind': 'integrated_operations'},
        {'tool_key': 'io2', 'display_name': 'Other integrated', 'kind': 'integrated_operations'},
        {'tool_key': 's', 'display_name': 'Strategic', 'kind': 'strategic'},
    ],
    'tools': [
        {'tool_key': 'p', 'display_name': 'Process', 'kind': 'process', 'components': []},
        {
            'tool_key': 'io',
            'display_name': 'Integrated',
            'kind': 'integrated_operations',
            'components': [],
        },
    ],
}


def _values(options):
    return {option['value'] for option in options}


def test_confirmed_reference_document_keeps_routing_and_visual_tools_separate():
    process = SimpleNamespace(
        tool_key='process',
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_release_id=SimpleNamespace(value='release-process'),
        components=(),
    )
    strategic = SimpleNamespace(
        tool_key='strategy',
        display_name='Strategy',
        kind=ToolConfigurationKind.STRATEGIC,
    )
    catalog = SimpleNamespace(
        catalog_revision='confirmed-1',
        tools=(process,),
        dependencies=SimpleNamespace(tools=(process, strategic)),
    )
    result = tool_reference_catalog_to_document(catalog)
    assert result is not None
    assert _values(tool_suggestions(result)) == {'process', 'strategy'}
    assert {item['tool_key'] for item in result['tools']} == {'process'}
    assert result['catalog_revision'] == 'confirmed-1'


def test_step_options_require_the_immediate_next_level():
    assert _values(
        routing_target_suggestions(REFERENCES, {'origin_tool_key': 'p', 'steps': []}, None)
    ) == {'io', 'io2'}
    assert _values(
        routing_target_suggestions(REFERENCES, {'origin_tool_key': 'io', 'steps': []}, None)
    ) == {'s'}
    assert routing_target_suggestions(REFERENCES, {'origin_tool_key': 's', 'steps': []}, None) == ()
    assert (
        routing_target_suggestions(REFERENCES, {'origin_tool_key': 'missing', 'steps': []}, None)
        == ()
    )


def test_next_step_uses_enabled_steps_sorted_by_step_order():
    route = {
        'origin_tool_key': 'p',
        'steps': [
            {'step_order': 3, 'target_tool_key': '', 'is_enabled': True},
            {'step_order': 2, 'target_tool_key': 'io', 'is_enabled': True},
            {'step_order': 1, 'target_tool_key': 'io2', 'is_enabled': False},
        ],
    }
    assert _values(routing_target_suggestions(REFERENCES, route, 1)) == {'io', 'io2'}
    assert _values(routing_target_suggestions(REFERENCES, route, 0)) == {'s'}
    assert routing_target_suggestions(REFERENCES, route, None) == ()


def test_visual_sync_never_invents_strategic_projection():
    document = {
        'rules': [
            {
                'escalation': {
                    'origin_tool_key': 'p',
                    'steps': [
                        {'step_order': 1, 'target_tool_key': 'io', 'is_enabled': True},
                        {'step_order': 2, 'target_tool_key': 's', 'is_enabled': True},
                    ],
                },
                'visual_targets': [],
            }
        ],
        'messages': [],
    }
    synced = synchronize_visual_targets(document, 0, REFERENCES)
    assert tuple(item['tool_key'] for item in synced['rules'][0]['visual_targets']) == ('p', 'io')
    assert document['rules'][0]['visual_targets'] == []


def test_editor_keeps_invalid_previous_destination_visible_for_correction():
    escalation = {
        'origin_tool_key': 'io',
        'steps': [
            {
                'step_order': 1,
                'target_tool_key': 'p',
                'is_enabled': True,
                'wait_minutes_from_previous_step': 20,
            },
        ],
    }
    panel = _escalation_editor(0, escalation, escalation['steps'], REFERENCES)
    target_field = panel.children[3].children[3]
    dropdown = target_field.children[1].children
    assert isinstance(dropdown, dcc.Dropdown)
    assert dropdown.value == 'p'
    assert _values(dropdown.options) == {'s', 'p'}
    invalid = next(option for option in dropdown.options if option['value'] == 'p')
    assert invalid['disabled'] is True
    assert 'no corresponde al siguiente nivel' in panel.children[3].children[4].children


def test_strategic_origin_has_no_add_step_action():
    panel = _escalation_editor(0, {'origin_tool_key': 's', 'steps': []}, [], REFERENCES)
    assert getattr(panel.children[2], 'id', None) is None
