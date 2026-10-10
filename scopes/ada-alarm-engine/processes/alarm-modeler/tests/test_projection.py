from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from ada.processes.alarm_modeler.projection import (
    AlarmModelerProjectionError,
    digest,
    has_semantic_change,
    project,
    validate_document,
)

KEY = {'alarm_configuration_revision': 'R1', 'confirmed_tool_catalog_revision': 'T1'}
REF = {
    'source_key': 'alarm-configuration',
    'result_id': 'alarm-materialization-' + 'a' * 64,
    'manifest_sha256': 'b' * 64,
    'resolution_key': KEY,
}


def source(alarms, *, at='2026-10-10T18:00:00Z', position=1):
    document = {
        'document_type': 'ada_alarm_engine_resolved_current_state',
        'schema_version': 1,
        'artifact_ref': deepcopy(REF),
        'journal_position': {'segment_id': 'segment', 'byte_offset': position, 'commit_id': 'c1'},
        'state': {'resolution_key': deepcopy(KEY), 'as_of': at, 'alarms': alarms},
    }
    document['sha256'] = digest(document)
    return document


def model(*names, visibility='VISIBLE'):
    return {
        'resolution_key': deepcopy(KEY),
        'alarms': [
            {
                'identity': {'family_key': 'f', 'alarm_key': name},
                'is_active': True,
                'visibility_mode': visibility,
                'display_name': name,
                'title': 'Title ' + name,
                'cause_template': '{value_1}',
                'kind': 'RISK',
                'criticality': 'C2',
                'business_category': 'SAFETY_HEALTH',
                'operational_areas': ['PLANT'],
                'color': 'YELLOW',
                'priority_group': 'group-' + name,
                'priority_order': 1,
                'messages': [],
                'default_deactivation_policy': {
                    'enabled': False, 'max_duration_hours': None, 'approval_required': False,
                },
                'visual_targets': [
                    {'tool_key': 'tool-a', 'component_keys': ['main'], 'subcomponents': [],
                     'process_projection_mode': None},
                ],
            }
            for name in names
        ],
    }


def alarm(name, *, priority='PREDOMINANT', managed=False, deactivated=False,
          status='ACTIVE', assigned=True):
    return {
        'identity': 'f/' + name,
        'priority_group': 'group-' + name,
        'occurrence_id': 'occ-' + name,
        'episode_id': 'ep-' + name,
        'started_at': '2026-10-10T17:00:00Z',
        'evaluation': {'status': status, 'evidence': {'contract_key': 'c', 'contract_version': '1',
                                                    'payload': {'value_1': 2}}, 'error': None},
        'priority': {'disposition': priority, 'blockers': []},
        'management_cycle': 1,
        'directly_managed': managed,
        'management_effect': {'effect_id': 'managed'} if managed else None,
        'deactivation_effect': {'effect_id': 'deactivated'} if deactivated else None,
        'technical_hold': None,
        'assignments': [{'tool_key': 'tool-a', 'assigned_at': '2026-10-10T17:00:00Z'}] if assigned else [],
        'pending_assignments': [],
    }


def built(alarms, *, model_names=None, time=None, tools=('tool-a',), previous=None,
          slots=6, rotation=30, at='2026-10-10T18:00:00Z', position=1):
    names = tuple(row['identity'].split('/')[-1] for row in alarms) if model_names is None else model_names
    return project(
        current=source(alarms, at=at, position=position),
        modeler_configuration=model(*names),
        publication_tool_keys=tools,
        previous=previous,
        now=datetime(2026, 10, 10, 18, tzinfo=UTC) if time is None else time,
        max_visible_slots=slots,
        rotation_seconds=rotation,
    )


def test_predominance_and_management_keep_live_but_remove_attention():
    result = built([
        alarm('normal'), alarm('managed', managed=True),
        alarm('deactivated', priority='DEACTIVATED', deactivated=True),
        alarm('eclipsed', priority='ECLIPSED'),
        alarm('error', status='ERROR'),
    ])
    tool = result['tools']['tool-a']
    assert set(tool['alarms']) == {
        'occ-normal', 'occ-managed', 'occ-deactivated', 'occ-error'
    }
    assert set(tool['operator_pool']) == {'occ-normal', 'occ-error'}
    assert tool['alarms']['occ-managed']['directly_managed'] is True
    assert tool['alarms']['occ-managed']['attention_required'] is False
    assert tool['alarms']['occ-error']['evaluation']['status'] == 'ERROR'
    assert tool['alarms']['occ-normal']['started_at'] == '2026-10-10T17:00:00Z'
    assert validate_document(result) == result


def test_visibility_trace_only_is_not_projected():
    result = project(
        current=source([alarm('a')]),
        modeler_configuration=model('a', visibility='TRACE_ONLY'),
        publication_tool_keys=('tool-a',),
        now=datetime(2026, 10, 10, tzinfo=UTC),
    )
    assert result['tools']['tool-a']['alarms'] == {}
    assert result['tools']['tool-a']['operator_view'] == []


def test_rotation_from_existing_pool_without_new_current():
    names = [f'a{i}' for i in range(7)]
    active = [alarm(name) for name in names]
    first = built(active, slots=3, rotation=30, time=datetime.fromtimestamp(0, tz=UTC))
    second = built(active, slots=3, rotation=30, time=datetime.fromtimestamp(30, tz=UTC), previous=first)
    assert first['tools']['tool-a']['operator_pool'] == second['tools']['tool-a']['operator_pool']
    assert first['tools']['tool-a']['operator_view'] != second['tools']['tool-a']['operator_view']
    assert has_semantic_change(first, second)


def test_elapsed_clock_does_not_rewrite_when_all_fit():
    first = built([alarm('a')], time=datetime.fromtimestamp(0, tz=UTC))
    second = built([alarm('a')], time=datetime.fromtimestamp(500, tz=UTC), previous=first)
    assert not has_semantic_change(first, second)


def test_changed_source_provenance_without_semantic_change_is_skip():
    first = built([alarm('a')], at='2026-10-10T18:00:00Z', position=1)
    second = built([alarm('a')], at='2026-10-10T18:01:00Z', position=2, previous=first)
    assert first['sha256'] != second['sha256']
    assert not has_semantic_change(first, second)


def test_last_alarm_closes_publishes_empty_once():
    previous = built([alarm('a')])
    empty = built([], model_names=('a',), previous=previous)
    assert empty['tools']['tool-a']['alarms'] == {}
    assert empty['tools']['tool-a']['operator_view'] == []
    assert has_semantic_change(previous, empty)
    again = built([], model_names=('a',), previous=empty)
    assert not has_semantic_change(empty, again)


def test_removed_tool_is_retired_with_empty_snapshot():
    old = built([alarm('a')])
    current = built([], model_names=(), tools=(), previous=old)
    assert current['tools']['tool-a']['retired'] is True
    assert current['tools']['tool-a']['alarms'] == {}
    assert has_semantic_change(old, current)
    assert not has_semantic_change(current, built([], model_names=(), tools=(), previous=current))


def test_management_change_updates_without_physical_change():
    previous = built([alarm('a')])
    changed = built([alarm('a', managed=True)], previous=previous)
    assert has_semantic_change(previous, changed)
    assert changed['tools']['tool-a']['operator_pool'] == []
    assert 'occ-a' in changed['tools']['tool-a']['alarms']


def test_routing_assignment_can_change_without_evidence_change():
    previous = built([alarm('a', assigned=False)])
    changed = built([alarm('a')], previous=previous)
    assert has_semantic_change(previous, changed)
    assert changed['tools']['tool-a']['operator_pool'] == ['occ-a']


def test_corruption_blocks_processing():
    document = source([alarm('a')])
    document['state']['alarms'][0]['directly_managed'] = True
    with pytest.raises(AlarmModelerProjectionError, match='checksum'):
        project(
            current=document, modeler_configuration=model('a'),
            publication_tool_keys=('tool-a',), now=datetime.now(UTC),
        )


def test_different_configuration_revision_is_rejected():
    config = model('a')
    config['resolution_key'] = {'alarm_configuration_revision': 'R2',
                                'confirmed_tool_catalog_revision': 'T1'}
    with pytest.raises(AlarmModelerProjectionError, match='revisions'):
        project(
            current=source([alarm('a')]), modeler_configuration=config,
            publication_tool_keys=('tool-a',), now=datetime.now(UTC),
        )


def test_duplicate_resolved_alarm_is_rejected():
    with pytest.raises(AlarmModelerProjectionError, match='Duplicate resolved'):
        built([alarm('a'), alarm('a')], model_names=('a',))


def test_initial_empty_state_is_publishable():
    empty = built([], model_names=(), tools=('tool-a',))
    assert empty['tools']['tool-a']['retired'] is False
    assert empty['tools']['tool-a']['alarms'] == {}
    assert empty['tools']['tool-a']['operator_view'] == []
    assert has_semantic_change(None, empty)
