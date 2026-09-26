import json
from copy import deepcopy

import pytest

from ada_command_center.web.alarms.configuration.web.authoring import (
    empty_authoring_document,
    set_message_field,
    set_visual_components,
    set_visual_subcomponents,
    synchronize_visual_targets,
)
from ada_command_center.web.alarms.configuration.web.callbacks import (
    _deletion_issue,
    _modal_shape,
)
from ada_command_center.web.alarms.configuration.web.families import (
    add_message_in_family,
    add_rule_in_family,
    family_catalog,
    initial_navigation,
)
from ada_command_center.web.alarms.configuration.web.pagination import list_page, list_pagination

CATALOG = {
    'tools': [
        {
            'tool_key': 'operations',
            'display_name': 'Operaciones Integradas',
            'kind': 'integrated_operations',
            'components': [
                {
                    'component_key': 'mine',
                    'display_name': 'Mina',
                    'subcomponents': [
                        {
                            'owner_component_key': 'owner-mine',
                            'subcomponent_key': 'crusher',
                            'display_name': 'Chancador',
                        },
                    ],
                },
            ],
        },
        {
            'tool_key': 'process',
            'display_name': 'Proceso',
            'kind': 'process',
            'components': [
                {'component_key': 'center', 'display_name': 'Centro', 'subcomponents': []},
            ],
        },
    ],
}


def _routed_document():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    rule = document['rules'][0]
    rule['escalation'] = {
        'origin_tool_key': 'operations',
        'steps': [
            {'target_tool_key': 'process', 'is_enabled': True, 'step_order': 1},
            {'target_tool_key': 'operations', 'is_enabled': True, 'step_order': 2},
        ],
    }
    return document


def test_visual_targets_are_derived_from_distinct_enabled_routing_tools():
    original = _routed_document()
    result = synchronize_visual_targets(original, 0, CATALOG)
    assert original['rules'][0]['visual_targets'] == []
    assert [entry['tool_key'] for entry in result['rules'][0]['visual_targets']] == [
        'operations',
        'process',
    ]
    assert all(
        entry['process_projection_mode'] is None for entry in result['rules'][0]['visual_targets']
    )


def test_routing_refresh_preserves_compatible_selections_without_dangling_targets():
    result = synchronize_visual_targets(_routed_document(), 0, CATALOG)
    result['rules'][0]['visual_targets'][1]['process_projection_mode'] = 'DISTRIBUTED'
    result['rules'][0]['escalation']['steps'][0]['is_enabled'] = False
    updated = synchronize_visual_targets(result, 0, CATALOG)
    assert [entry['tool_key'] for entry in updated['rules'][0]['visual_targets']] == ['operations']
    result['rules'][0]['escalation']['steps'][0]['is_enabled'] = True
    preserved = synchronize_visual_targets(result, 0, CATALOG)
    assert preserved['rules'][0]['visual_targets'][1]['process_projection_mode'] == 'DISTRIBUTED'


def test_visual_subcomponents_are_bound_to_selected_catalog_components():
    document = synchronize_visual_targets(_routed_document(), 0, CATALOG)
    selected = set_visual_components(document, 0, 0, ['mine'], CATALOG)
    token = json.dumps(['owner-mine', 'crusher'], separators=(',', ':'))
    updated = set_visual_subcomponents(selected, 0, 0, [token], CATALOG)
    assert updated['rules'][0]['visual_targets'][0]['subcomponents'] == [
        {'owner_component_key': 'owner-mine', 'subcomponent_key': 'crusher'},
    ]
    removed = set_visual_components(updated, 0, 0, [], CATALOG)
    assert removed['rules'][0]['visual_targets'][0]['subcomponents'] == []
    with pytest.raises(ValueError, match='catalog'):
        set_visual_components(updated, 0, 0, ['invented'], CATALOG)
    with pytest.raises(ValueError, match='catalog'):
        set_visual_subcomponents(removed, 0, 0, [token], CATALOG)


def test_message_override_selection_has_single_explicit_semantics():
    document = add_message_in_family(empty_authoring_document(), None)
    allowed = set_message_field(document, 0, 'deactivation_policy', 'ALLOW')
    assert allowed['messages'][0]['scope'] == 'GLOBAL'
    assert allowed['messages'][0]['family_key'] is None
    assert allowed['messages'][0]['deactivation_override']['enabled'] is True
    blocked = set_message_field(allowed, 0, 'deactivation_policy', 'DENY')
    assert blocked['messages'][0]['deactivation_override'] == {
        'enabled': False,
        'max_duration_hours': None,
        'approval_required': False,
    }
    inherited = set_message_field(blocked, 0, 'deactivation_policy', 'INHERIT')
    assert inherited['messages'][0]['deactivation_override'] is None
    with pytest.raises(ValueError, match='Invalid'):
        set_message_field(inherited, 0, 'deactivation_policy', 'MAYBE')


def test_empty_family_keys_cannot_appear_as_blank_cards():
    document = empty_authoring_document()
    document['messages'].append(
        {'scope': 'FAMILY', 'family_key': '', 'message_key': '', 'is_active': None}
    )
    document['rules'].append({'identity': {'family_key': '', 'alarm_key': ''}})
    assert family_catalog(document).families == ()


def test_deletion_blocks_references_without_removing_other_entities():
    document = add_rule_in_family(empty_authoring_document(), 'mine')
    document = add_rule_in_family(document, 'mine')
    document['rules'][1]['reappearance']['special_conditions'] = [
        deepcopy(document['rules'][0]['identity'])
    ]
    assert _deletion_issue(document, 'rule', 0) is not None
    document = add_message_in_family(document, None)
    document['messages'][0]['message_key'] = 'maintenance'
    document['rules'][1]['message_keys'] = ['maintenance']
    assert _deletion_issue(document, 'message', 0) is not None
    assert _deletion_issue(document, 'rule', 1) is None


def test_regular_field_edits_do_not_request_modal_reconstruction():
    document = _routed_document()
    navigation = {
        **initial_navigation(),
        'page': 'family',
        'family_key': 'mine',
        'rule_index': 0,
        'section': 'behavior',
    }
    before = _modal_shape(document, navigation)
    document['rules'][0]['escalation']['steps'][0]['wait_minutes_from_previous_step'] = 99
    assert _modal_shape(document, navigation) == before
    document['rules'][0]['criticality'] = 'C3'
    assert _modal_shape(document, navigation) != before


def test_pagination_matches_manager_even_with_one_item():
    page = list_page(('only',), initial_navigation(), 'families')
    control = list_pagination(page, 'families')
    assert control is not None
    assert 'Mostrando' in control.children[0].children
    assert len(control.children[1].children) >= 2
