from __future__ import annotations

from datetime import datetime, timezone

from ada.web.alarms.live_surface.live import (
    build_live_alarm_cards,
    resolve_live_alarm_cards,
)


def _data():
    return {
        'tool_key': 'io',
        'availability': 'ready',
        'live': {
            'tool_key': 'io', 'schema_version': 2, 'retired': False,
            'max_visible_slots': 4,
            'alarms': {
                'b': {'title': 'Second', 'cause_text': 'Reason', 'color': 'YELLOW',
                      'criticality': 'C2', 'started_at': '2026-10-12T12:00:00Z',
                      'visual_target': {'tool_key': 'io', 'component_keys': ['cmp_2'],
                                        'subcomponents': [{'owner_component_key': 'cmp_2',
                                                           'subcomponent_key': 'sub_2'}]}},
                'a': {'title': 'First', 'cause_text': 'Event', 'color': 'RED',
                      'criticality': 'C1', 'business_category': 'PRODUCTIVITY', 'kind': 'IMPACT', 'started_at': '2026-10-12T12:00:00Z',
                      'visual_target': {'tool_key': 'io', 'component_keys': ['cmp_1'],
                                        'subcomponents': [{'owner_component_key': 'cmp_1',
                                                           'subcomponent_key': 'sub_1'}]}},
            },
            'operator_view': [
                {'slot': 3, 'occurrence_id': 'b'},
                {'slot': 1, 'occurrence_id': 'a'},
            ],
        },
    }


def test_live_cards_follow_operator_slots_and_resolved_targets():
    capacity, cards = resolve_live_alarm_cards(
        _data(), tool_key='io', now=datetime(2026, 10, 12, 12, 12, tzinfo=timezone.utc),
    )
    assert capacity == 4
    assert [card.occurrence_id for card in cards] == ['a', 'b']
    assert [card.slot for card in cards] == [1, 3]
    assert [card.color for card in cards] == ['RED', 'YELLOW']
    assert cards[0].elapsed == '12 min'
    assert cards[0].category == 'IMPACT · PRODUCTIVITY'
    assert cards[1].component_keys == ('cmp_2',)
    assert cards[1].subcomponent_keys == ('sub_2',)


def test_ready_empty_preserves_capacity_and_missing_hides_cards():
    data = _data()
    data['live']['operator_view'] = []
    assert resolve_live_alarm_cards(data, tool_key='io') == (4, ())
    assert resolve_live_alarm_cards(_data(), tool_key='another') == (1, ())
    assert resolve_live_alarm_cards({'tool_key': 'io', 'live': None}, tool_key='io') == (1, ())


def test_retired_and_unresolved_target_do_not_create_false_routes():
    data = _data()
    data['live']['retired'] = True
    assert resolve_live_alarm_cards(data, tool_key='io') == (1, ())
    data['live']['retired'] = False
    data['live']['alarms']['a']['visual_target']['tool_key'] = 'another'
    assert resolve_live_alarm_cards(data, tool_key='io')[1][0].component_keys == ()


def test_rendered_cards_have_stable_occurrence_and_target_metadata():
    rendered = build_live_alarm_cards(_data(), tool_key='io')
    assert len(rendered) == 2
    first = rendered[0].to_plotly_json()['props']
    assert first['data-ada-alarm-occurrence-id'] == 'a'
    assert first['data-ada-alarm-color'] == 'RED'
    assert first['data-ada-alarm-target-components'] == 'cmp_1'
    assert first['data-ada-alarm-target-subcomponents'] == 'sub_1'
    assert first['style']['gridColumn'] == '1'


def test_distributed_group_keeps_slot_without_inventing_rotation():
    data = _data()
    data['live']['operator_view'] = [
        {'slot': 4, 'group': {
            'kind': 'DISTRIBUTED',
            'visible_by_area': {'MINE': ['a'], 'PLANT': ['b']},
            'total_by_area': {'MINE': 2, 'PLANT': 3},
        }},
    ]
    capacity, cards = resolve_live_alarm_cards(data, tool_key='io')
    assert capacity == 4
    assert len(cards) == 1
    assert cards[0].grouped is True
    assert cards[0].component_keys == ()
    assert cards[0].slot == 4


def test_live_cards_are_keyboard_selectable_without_exposing_distributed_group_as_action():
    data = _data()
    card = build_live_alarm_cards(data, tool_key='io')[0]
    props = card.to_plotly_json()['props']
    assert props['role'] == 'button'
    assert props['tabIndex'] == 0
    assert props['aria-pressed'] == 'false'
    assert 'First' in props['aria-label']

    data['live']['operator_view'] = [{'slot': 4, 'group': {
        'kind': 'DISTRIBUTED', 'visible_by_area': {'MINE': ['a']},
        'total_by_area': {'MINE': 1},
    }}]
    grouped = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert grouped['role'] == 'group'
    assert 'tabIndex' not in grouped


def test_distributed_group_respects_projected_area_order_and_targets():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['operator_view'] = [{'slot': 6, 'group': {
        'kind': 'DISTRIBUTED',
        'visible_by_area': {'MINE': ['b', 'a'], 'PLANT': ['a']},
        'total_by_area': {'MINE': 3, 'PLANT': 2},
    }}]
    _, cards = resolve_live_alarm_cards(data, tool_key='io')
    group = cards[0]
    assert group.grouped
    assert group.slot == 6
    assert group.cause == 'Mina 2/3 · Planta 1/2'
    assert [(item.area, item.occurrence_id) for item in group.group_members] == [
        ('MINE', 'b'), ('MINE', 'a'), ('PLANT', 'a'),
    ]
    assert [item.color for item in group.group_members] == ['YELLOW', 'RED', 'RED']
    assert [item.component_keys for item in group.group_members] == [
        ('cmp_2',), ('cmp_1',), ('cmp_1',),
    ]
    assert [item.subcomponent_keys for item in group.group_members] == [
        ('sub_2',), ('sub_1',), ('sub_1',),
    ]


def test_distributed_carousel_only_renders_selected_members_from_operator_view():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['alarms']['unselected'] = {
        'title': 'Should not display', 'color': 'RED',
        'visual_target': {'tool_key': 'io', 'component_keys': ['not_selected']},
    }
    data['live']['operator_view'] = [{'slot': 6, 'group': {
        'kind': 'DISTRIBUTED',
        'visible_by_area': {'MINE': ['a'], 'PLANT': ['b']},
        'total_by_area': {'MINE': 2, 'PLANT': 2},
    }}]
    group = build_live_alarm_cards(data, tool_key='io')[0]
    props = group.to_plotly_json()['props']
    assert props['role'] == 'group'
    assert props['style']['gridColumn'] == '6'
    slides = group.children[1].children
    assert len(slides) == 2
    assert [item.to_plotly_json()['props']['data-ada-alarm-occurrence-id']
            for item in slides] == ['a', 'b']
    assert [item.to_plotly_json()['props']['hidden'] for item in slides] == [False, True]
    assert [item.to_plotly_json()['props']['data-ada-alarm-target-components']
            for item in slides] == ['cmp_1', 'cmp_2']


def test_distributed_group_with_no_visible_members_remains_noninteractive():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['operator_view'] = [{'slot': 6, 'group': {
        'kind': 'DISTRIBUTED',
        'visible_by_area': {'MINE': []},
        'total_by_area': {'MINE': 3},
    }}]
    group = build_live_alarm_cards(data, tool_key='io')[0]
    props = group.to_plotly_json()['props']
    assert props['data-ada-alarm-grouped'] == 'true'
    assert 'role' not in props
    assert props['data-ada-alarm-target-components'] == ''


def test_integrated_cards_keep_display_location_distinct_from_affected_components():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['operator_view'] = [{'slot': 4, 'occurrence_id': 'a'}]
    target = data['live']['alarms']['a']['visual_target']
    target['tool_kind'] = 'integrated_operations'
    target['component_keys'] = ['cmp_1', 'cmp_2']
    target['display_component_key'] = 'cmp_2'
    target['display_scope'] = 'plant'
    capacity, cards = resolve_live_alarm_cards(data, tool_key='io')
    assert capacity == 6
    assert cards[0].slot == 4
    assert cards[0].display_component_key == 'cmp_2'
    assert cards[0].display_scope == 'plant'
    assert cards[0].component_keys == ('cmp_1', 'cmp_2')
    assert cards[0].subcomponent_keys == ('sub_1',)
    props = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert props['data-ada-alarm-display-component-key'] == 'cmp_2'
    assert props['data-ada-alarm-display-scope'] == 'plant'
    assert props['data-ada-alarm-target-components'] == 'cmp_1 cmp_2'
    assert props['style']['gridColumn'] == '4'


def test_incomplete_integrated_location_does_not_invent_a_component():
    data = _data()
    target = data['live']['alarms']['a']['visual_target']
    target['tool_kind'] = 'integrated_operations'
    target['display_component_key'] = 'missing'
    target['display_scope'] = 'mine'
    card = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert card['data-ada-alarm-display-component-key'] == ''
    assert card['data-ada-alarm-display-scope'] == ''
    target['display_component_key'] = 'cmp_1'
    target['display_scope'] = 'unknown'
    card = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert card['data-ada-alarm-display-component-key'] == ''


def test_process_cards_preserve_original_position_without_integrated_placement():
    data = _data()
    target = data['live']['alarms']['a']['visual_target']
    target['tool_kind'] = 'process'
    target['display_component_key'] = 'cmp_1'
    target['display_scope'] = 'plant'
    props = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert props['style']['gridColumn'] == '1'
    assert props['data-ada-alarm-display-component-key'] == ''
    assert props['data-ada-alarm-target-components'] == 'cmp_1'
