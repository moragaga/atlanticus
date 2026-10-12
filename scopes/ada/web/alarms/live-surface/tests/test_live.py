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
