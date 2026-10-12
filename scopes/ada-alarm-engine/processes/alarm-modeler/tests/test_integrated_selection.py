from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from ada.processes.alarm_modeler.integrated_selection import (
    IntegratedAlarmSelectionError,
    is_integrated_tool,
    project_integrated_slots,
    validate_integrated_slots,
)
from ada.processes.alarm_modeler.projection import digest, project, validate_document

from .test_projection import alarm, model, source


def _configuration(placements: dict[str, tuple[str, str]], *, priority: dict[str, int] | None = None):
    definition = model(*placements)
    for row in definition['alarms']:
        name = row['identity']['alarm_key']
        scope, component = placements[name]
        row['priority_order'] = (priority or {}).get(name, 1)
        row['operational_areas'] = ['MINE', 'PLANT']
        row['visual_targets'] = [{
            'tool_key': 'tool-a',
            'tool_kind': 'integrated_operations',
            'component_keys': [component, 'shared'],
            'display_component_key': component,
            'display_scope': scope,
            'subcomponents': [{'owner_component_key': 'shared', 'subcomponent_key': 'sensor'}],
            'process_projection_mode': None,
        }]
    return definition


def _projection(placements: dict[str, tuple[str, str]], *, managed=(), priority=None):
    return project(
        current=source([alarm(name, managed=name in managed) for name in placements]),
        modeler_configuration=_configuration(placements, priority=priority),
        publication_tool_keys=('tool-a',),
        now=datetime(2026, 10, 10, 18, tzinfo=UTC),
        max_visible_slots=6,
        rotation_seconds=30,
    )


def test_integrated_uses_first_eligible_alarm_per_component_and_three_slots_per_area():
    places = {
        'a2': ('mine', 'a'), 'a1': ('mine', 'a'),
        'b': ('mine', 'b'), 'c': ('mine', 'c'), 'd': ('mine', 'd'),
        'p1': ('plant', 'p'), 'p2': ('plant', 'q'),
        'p3': ('plant', 'r'), 'p4': ('plant', 's'),
    }
    result = _projection(places, priority={'a1': 1, 'a2': 2})
    tool = result['tools']['tool-a']
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-a1'},
        {'slot': 2, 'occurrence_id': 'occ-b'},
        {'slot': 3, 'occurrence_id': 'occ-c'},
        {'slot': 4, 'occurrence_id': 'occ-p1'},
        {'slot': 5, 'occurrence_id': 'occ-p2'},
        {'slot': 6, 'occurrence_id': 'occ-p3'},
    ]
    assert len(tool['operator_pool']) == len(places)
    assert tool['meta']['rotation_pending'] is False
    assert tool['alarms']['occ-a1']['visual_target']['display_component_key'] == 'a'
    assert tool['alarms']['occ-a1']['visual_target']['display_scope'] == 'mine'
    assert tool['alarms']['occ-a1']['visual_target']['component_keys'] == ['a', 'shared']
    assert validate_document(result) == result


def test_queue_promotes_second_when_first_is_no_longer_eligible():
    places = {'a1': ('mine', 'a'), 'a2': ('mine', 'a'), 'b': ('plant', 'b')}
    initial = _projection(places, priority={'a1': 1, 'a2': 2})
    next_view = _projection(places, managed=('a1',), priority={'a1': 1, 'a2': 2})
    assert [item['occurrence_id'] for item in initial['tools']['tool-a']['operator_view']] == [
        'occ-a1', 'occ-b',
    ]
    assert [item['occurrence_id'] for item in next_view['tools']['tool-a']['operator_view']] == [
        'occ-a2', 'occ-b',
    ]


def test_operator_scope_follows_resolved_display_component_not_rule_areas():
    places = {'p': ('plant', 'p'), 'm': ('mine', 'm')}
    tool = _projection(places)['tools']['tool-a']
    assert tool['operator_view'] == [
        {'slot': 1, 'occurrence_id': 'occ-m'},
        {'slot': 4, 'occurrence_id': 'occ-p'},
    ]


def test_integrated_rejects_invalid_component_and_area():
    alarms = {
        'a': {'visual_target': {
            'tool_kind': 'integrated_operations', 'display_component_key': 'a',
            'component_keys': ['a'], 'display_scope': 'mine',
        }},
    }
    assert project_integrated_slots(['a'], alarms, max_visible_slots=6) == [
        {'slot': 1, 'occurrence_id': 'a'},
    ]
    with pytest.raises(IntegratedAlarmSelectionError, match='six visible slots'):
        project_integrated_slots(['a'], alarms, max_visible_slots=4)
    alarms['a']['visual_target']['display_scope'] = 'other'
    with pytest.raises(IntegratedAlarmSelectionError, match='display scope'):
        project_integrated_slots(['a'], alarms, max_visible_slots=6)
    alarms['a']['visual_target']['display_scope'] = 'mine'
    alarms['a']['visual_target']['component_keys'] = ['other']
    with pytest.raises(IntegratedAlarmSelectionError, match='display component'):
        project_integrated_slots(['a'], alarms, max_visible_slots=6)


def test_validator_rejects_component_overlap_and_cross_area_slot():
    places = {'a': ('mine', 'a'), 'b': ('mine', 'b')}
    result = _projection(places)
    tool = deepcopy(result['tools']['tool-a'])
    assert is_integrated_tool(tool)
    tool['operator_view'][1]['occurrence_id'] = 'occ-a'
    with pytest.raises(IntegratedAlarmSelectionError, match='component'):
        validate_integrated_slots(tool)
    tool = deepcopy(result['tools']['tool-a'])
    tool['operator_view'][0]['slot'] = 4
    with pytest.raises(IntegratedAlarmSelectionError, match='component'):
        validate_integrated_slots(tool)
    corrupted = deepcopy(result)
    corrupted['tools']['tool-a'] = tool
    corrupted['sha256'] = digest({k: v for k, v in corrupted.items() if k != 'sha256'})
    with pytest.raises(IntegratedAlarmSelectionError):
        validate_document(corrupted)


def test_no_integrated_alarm_keeps_nonintegrated_rotation():
    assert not is_integrated_tool({'alarms': {}})
    tool = _projection({'m': ('mine', 'm')})['tools']['tool-a']
    assert is_integrated_tool(tool)
