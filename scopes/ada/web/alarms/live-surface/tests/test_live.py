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
            'tool_key': 'io',
            'schema_version': 2,
            'retired': False,
            'max_visible_slots': 4,
            'alarms': {
                'b': {
                    'title': 'Second',
                    'cause_text': 'Reason',
                    'color': 'YELLOW',
                    'criticality': 'C2',
                    'started_at': '2026-10-12T12:00:00Z',
                    'visual_target': {
                        'tool_key': 'io',
                        'component_keys': ['cmp_2'],
                        'subcomponents': [
                            {'owner_component_key': 'cmp_2', 'subcomponent_key': 'sub_2'}
                        ],
                    },
                },
                'a': {
                    'title': 'First',
                    'cause_text': 'Event',
                    'color': 'RED',
                    'criticality': 'C1',
                    'business_category': 'PRODUCTIVITY',
                    'kind': 'IMPACT',
                    'started_at': '2026-10-12T12:00:00Z',
                    'visual_target': {
                        'tool_key': 'io',
                        'component_keys': ['cmp_1'],
                        'subcomponents': [
                            {'owner_component_key': 'cmp_1', 'subcomponent_key': 'sub_1'}
                        ],
                    },
                },
            },
            'operator_view': [
                {'slot': 3, 'occurrence_id': 'b'},
                {'slot': 1, 'occurrence_id': 'a'},
            ],
        },
    }


def test_live_cards_follow_operator_slots_and_resolved_targets():
    capacity, cards = resolve_live_alarm_cards(
        _data(),
        tool_key='io',
        now=datetime(2026, 10, 12, 12, 12, tzinfo=timezone.utc),
    )
    assert capacity == 4
    assert [card.occurrence_id for card in cards] == ['a', 'b']
    assert [card.slot for card in cards] == [1, 3]
    assert [card.color for card in cards] == ['RED', 'YELLOW']
    assert cards[0].elapsed == '12 min'
    assert cards[0].category == 'Impacto · Productividad'
    assert cards[1].component_keys == ('cmp_2',)
    assert cards[1].subcomponent_addresses == (('cmp_2', 'sub_2'),)


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


def test_subcomponent_identity_includes_its_component_owner():
    data = _data()
    target = data['live']['alarms']['a']['visual_target']
    target['component_keys'] = ['cmp_1', 'cmp_2']
    target['subcomponents'] = [
        {'owner_component_key': 'cmp_1', 'subcomponent_key': 'shared'},
        {'owner_component_key': 'cmp_2', 'subcomponent_key': 'shared'},
    ]
    card = build_live_alarm_cards(data, tool_key='io')[0]
    assert card.to_plotly_json()['props']['data-ada-alarm-target-addresses'] == (
        '[["cmp_1","shared"],["cmp_2","shared"]]'
    )


def test_subcomponent_target_outside_component_route_is_preserved():
    data = _data()
    data['live']['alarms']['a']['visual_target']['subcomponents'] = [
        {'owner_component_key': 'cmp_2', 'subcomponent_key': 'sub_2'},
    ]
    card = resolve_live_alarm_cards(data, tool_key='io')[1][0]
    assert card.component_keys == ('cmp_1',)
    assert card.subcomponent_addresses == (('cmp_2', 'sub_2'),)


def test_rendered_cards_have_stable_occurrence_and_target_metadata():
    rendered = build_live_alarm_cards(_data(), tool_key='io')
    assert len(rendered) == 2
    first = rendered[0].to_plotly_json()['props']
    assert first['data-ada-alarm-occurrence-id'] == 'a'
    assert first['data-ada-alarm-color'] == 'RED'
    assert first['data-ada-alarm-target-components'] == 'cmp_1'
    assert first['data-ada-alarm-target-addresses'] == '[["cmp_1","sub_1"]]'
    assert first['style']['gridColumn'] == '1'


def test_distributed_group_keeps_slot_without_inventing_rotation():
    data = _data()
    data['live']['operator_view'] = [
        {
            'slot': 4,
            'group': {
                'kind': 'DISTRIBUTED',
                'visible_by_area': {'MINE': ['a'], 'PLANT': ['b']},
                'total_by_area': {'MINE': 2, 'PLANT': 3},
            },
        },
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

    data['live']['operator_view'] = [
        {
            'slot': 4,
            'group': {
                'kind': 'DISTRIBUTED',
                'visible_by_area': {'MINE': ['a']},
                'total_by_area': {'MINE': 1},
            },
        }
    ]
    grouped = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert grouped['role'] == 'group'
    assert 'tabIndex' not in grouped


def test_distributed_group_respects_projected_area_order_and_targets():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['operator_view'] = [
        {
            'slot': 6,
            'group': {
                'kind': 'DISTRIBUTED',
                'visible_by_area': {'MINE': ['b', 'a'], 'PLANT': ['a']},
                'total_by_area': {'MINE': 3, 'PLANT': 2},
            },
        }
    ]
    _, cards = resolve_live_alarm_cards(data, tool_key='io')
    group = cards[0]
    assert group.grouped
    assert group.slot == 6
    assert group.cause == 'Mina 2/3 · Planta 1/2'
    assert [(item.area, item.occurrence_id) for item in group.group_members] == [
        ('MINE', 'b'),
        ('MINE', 'a'),
        ('PLANT', 'a'),
    ]
    assert [item.color for item in group.group_members] == ['YELLOW', 'RED', 'RED']
    assert [item.component_keys for item in group.group_members] == [
        ('cmp_2',),
        ('cmp_1',),
        ('cmp_1',),
    ]
    assert [item.subcomponent_addresses for item in group.group_members] == [
        (('cmp_2', 'sub_2'),),
        (('cmp_1', 'sub_1'),),
        (('cmp_1', 'sub_1'),),
    ]


def test_distributed_carousel_only_renders_selected_members_from_operator_view():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['alarms']['unselected'] = {
        'title': 'Should not display',
        'color': 'RED',
        'visual_target': {'tool_key': 'io', 'component_keys': ['not_selected']},
    }
    data['live']['operator_view'] = [
        {
            'slot': 6,
            'group': {
                'kind': 'DISTRIBUTED',
                'visible_by_area': {'MINE': ['a'], 'PLANT': ['b']},
                'total_by_area': {'MINE': 2, 'PLANT': 2},
            },
        }
    ]
    group = build_live_alarm_cards(data, tool_key='io')[0]
    props = group.to_plotly_json()['props']
    assert props['role'] == 'group'
    assert props['style']['gridColumn'] == '6'
    slides = group.children[1].children
    assert len(slides) == 2
    assert [item.to_plotly_json()['props']['data-ada-alarm-occurrence-id'] for item in slides] == [
        'a',
        'b',
    ]
    assert [item.to_plotly_json()['props']['hidden'] for item in slides] == [False, True]
    assert [
        item.to_plotly_json()['props']['data-ada-alarm-target-components'] for item in slides
    ] == ['cmp_1', 'cmp_2']


def test_distributed_group_with_no_visible_members_remains_noninteractive():
    data = _data()
    data['live']['max_visible_slots'] = 6
    data['live']['operator_view'] = [
        {
            'slot': 6,
            'group': {
                'kind': 'DISTRIBUTED',
                'visible_by_area': {'MINE': []},
                'total_by_area': {'MINE': 3},
            },
        }
    ]
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
    assert cards[0].subcomponent_addresses == (('cmp_1', 'sub_1'),)
    props = build_live_alarm_cards(data, tool_key='io')[0].to_plotly_json()['props']
    assert props['data-ada-alarm-display-component-key'] == 'cmp_2'
    assert props['data-ada-alarm-display-scope'] == 'plant'
    assert props['data-ada-alarm-target-components'] == 'cmp_1 cmp_2'
    assert props['style']['gridColumn'] == '4'


def test_integrated_snapshot_renders_both_mine_and_flotation_with_their_real_ids():
    data = _data()
    document = data['live']
    document['max_visible_slots'] = 6
    mine = 'cmp_general_mina_6df268db211b'
    flotation = 'cmp_flotacion_9bbf64c07ea7'
    document['alarms'] = {
        'occ-mp10': {
            'title': 'MP10', 'color': 'YELLOW',
            'visual_target': {
                'tool_key': 'io', 'tool_kind': 'integrated_operations',
                'component_keys': [mine, 'cmp_transporte_67b979e9ab49'],
                'display_component_key': mine, 'display_scope': 'mine',
                'subcomponents': [
                    {'owner_component_key': mine, 'subcomponent_key': 'sub_mp10_7c12dfcc7294'},
                ],
            },
        },
        'occ-tk050': {
            'title': 'TK-050', 'color': 'RED',
            'visual_target': {
                'tool_key': 'io', 'tool_kind': 'integrated_operations',
                'component_keys': [flotation],
                'display_component_key': flotation, 'display_scope': 'plant',
                'subcomponents': [
                    {'owner_component_key': flotation,
                     'subcomponent_key': 'sub_selectiva_13ecce0283b4'},
                ],
            },
        },
    }
    document['operator_view'] = [
        {'occurrence_id': 'occ-mp10', 'slot': 1},
        {'occurrence_id': 'occ-tk050', 'slot': 4},
    ]
    capacity, cards = resolve_live_alarm_cards(data, tool_key='io')
    assert capacity == 6
    assert [(card.title, card.slot, card.display_component_key) for card in cards] == [
        ('MP10', 1, mine), ('TK-050', 4, flotation),
    ]
    rendered = build_live_alarm_cards(data, tool_key='io')
    assert [card.to_plotly_json()['props']['data-ada-alarm-slot'] for card in rendered] == [
        '1', '4',
    ]
    assert rendered[1].to_plotly_json()['props']['data-ada-alarm-target-addresses'] == (
        f'[["{flotation}","sub_selectiva_13ecce0283b4"]]'
    )


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


def test_category_translations_and_icons_are_presentation_only():
    expected = (
        ('ECOLOGY', 'Medio Ambiente', 'ecology'),
        ('PRODUCTIVITY', 'Productividad', 'productivity'),
        ('SAFETY', 'Seguridad y Salud', 'safety'),
        ('SAFETY_HEALTH', 'Seguridad y Salud', 'safety'),
        ('COSTS', 'Costos', 'costs'),
    )
    for category, label, icon in expected:
        data = _data()
        data['live']['alarms']['a']['business_category'] = category
        _, cards = resolve_live_alarm_cards(data, tool_key='io')
        assert cards[0].category == f'Impacto · {label}'
        assert cards[0].category_icon == icon


def test_alarm_card_has_original_header_body_and_inert_actions():
    card = build_live_alarm_cards(_data(), tool_key='io')[0]
    header, body, footer = card.children
    assert 'ada-alarm-live-card__header' == header.className
    assert 'ada-alarm-live-card__body' == body.className
    assert 'ada-alarm-live-card__footer' == footer.className
    header_icon = header.children[0].children[0]
    assert header_icon.className.endswith('--productivity')
    assert header_icon.to_plotly_json()['props']['aria-hidden'] == 'true'
    assert header_icon.src.endswith('/img/alarms/productividad.svg')
    assert header_icon.alt == ''
    actions = footer.children[1].children
    assert [action.children for action in actions] == ['Información', 'Gestionar']
    assert all(action.disabled for action in actions)
