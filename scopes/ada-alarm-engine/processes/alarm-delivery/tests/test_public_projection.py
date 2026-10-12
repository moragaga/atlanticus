from __future__ import annotations

from copy import deepcopy

import pytest

from ada.processes.alarm_delivery.contract import plan_tool_deliveries
from ada.processes.alarm_delivery.public_projection import (
    AlarmLiveProjectionError,
    public_tool_projection,
)
from ada.processes.alarm_delivery.transport import live_document

from .test_contract import _destinations, _seal, _source, _tool


def _alarm(key, area='MINE'):
    return {
        'alarm_identity': 'family/' + key,
        'occurrence_id': key,
        'episode_id': 'episode-' + key,
        'started_at': '2026-10-11T15:00:00Z',
        'display_name': key,
        'title': 'Alarm ' + key,
        'cause_text': 'Pressure 132 bar',
        'criticality': 'C2',
        'color': 'YELLOW',
        'operational_areas': [area],
        'visual_target': {'tool_key': 'tool_a', 'component_keys': ['main'], 'subcomponents': [],
                          'process_projection_mode': 'DISTRIBUTED'},
        'management_cycle': 2,
        'directly_managed': False,
        'attention_required': True,
        'evaluation': {'status': 'ACTIVE', 'evidence': {'payload': {'private': 'value'}}},
        'technical_hold': {'started_at': 'private'},
        'priority': {'blockers': ['private']},
    }


def _candidate(tool):
    src = _source(tools={'tool_a': tool})
    return plan_tool_deliveries(
        modeler_document=src,
        destination_identities={'tool_a': 'cosmos-a/db/live'},
        confirmations={},
    ).pending[0]


def test_public_projection_drops_internal_fields_and_retains_action_identity():
    tool = _tool('tool_a', alarms={'a': _alarm('a')}, view=[{'slot': 1, 'occurrence_id': 'a'}])
    tool['operator_pool'] = ['a']
    tool['meta']['live_count'] = 1
    tool['meta']['attention_count'] = 1
    live = live_document(_candidate(tool))
    assert live['schema_version'] == 2
    assert live['operator_view'] == [{'slot': 1, 'occurrence_id': 'a'}]
    assert live['alarms']['a']['cause_text'] == 'Pressure 132 bar'
    assert live['alarms']['a']['management_cycle'] == 2
    assert live['alarms']['a']['visual_target']['component_keys'] == ['main']
    assert not {'operator_pool', 'meta', 'artifact_ref', 'source_journal_position'} & set(live)
    assert not {'evaluation', 'technical_hold', 'priority'} & set(live['alarms']['a'])


def test_distributed_group_publishes_selected_by_area_without_full_internal_queue():
    alarms = {str(i): _alarm(str(i), 'MINE' if i < 4 else 'PLANT') for i in range(6)}
    alarms['0']['operational_areas'] = ['MINE', 'PLANT']
    view = [{'slot': 6, 'group': {'kind': 'DISTRIBUTED', 'occurrence_ids': list(alarms)}}]
    tool = _tool('tool_a', alarms=alarms, view=view)
    tool['operator_pool'] = list(alarms)
    tool['meta']['live_count'] = 6
    tool['meta']['attention_count'] = 6
    tool['meta']['queue_in_queue'] = {
        'slots_per_area': 3,
        'visible_by_area': {'MINE': ['0', '1', '2'], 'PLANT': ['0', '4', '5']},
    }
    live = live_document(_candidate(tool))
    group = live['operator_view'][0]['group']
    assert group == {
        'kind': 'DISTRIBUTED',
        'visible_by_area': {'MINE': ['0', '1', '2'], 'PLANT': ['0', '4', '5']},
        'total_by_area': {'MINE': 4, 'PLANT': 3},
    }
    assert 'occurrence_ids' not in group
    assert 'queue_in_queue' not in live
    assert '0' in live['alarms']


def test_invalid_group_selection_is_rejected_before_publication():
    tool = _tool('tool_a', alarms={'a': _alarm('a'), 'b': _alarm('b')},
                 view=[{'slot': 6, 'group': {'kind': 'DISTRIBUTED', 'occurrence_ids': ['a', 'b']}}])
    tool['meta']['queue_in_queue'] = {
        'slots_per_area': 3, 'visible_by_area': {'MINE': ['missing']},
    }
    with pytest.raises(AlarmLiveProjectionError, match='area selection'):
        public_tool_projection(tool)


def test_semantic_hash_tracks_only_public_tool_content_and_effective_revision():
    tool = _tool('tool_a', alarms={'a': _alarm('a')}, view=[{'slot': 1, 'occurrence_id': 'a'}])
    tool['operator_pool'] = ['a']
    source = _source(tools={'tool_a': tool})
    dest = {'tool_a': 'cosmos-a/db/live'}
    initial = plan_tool_deliveries(modeler_document=source, destination_identities=dest, confirmations={})
    confirm = {'tool_a': initial.pending[0].confirmation()}
    invisible = deepcopy(source)
    invisible['tools']['tool_a']['operator_pool'] = ['a', 'internal-only']
    invisible['tools']['tool_a']['meta']['rotation_pending'] = True
    assert not plan_tool_deliveries(modeler_document=_seal(invisible),
                                    destination_identities=dest, confirmations=confirm).pending
    changed = deepcopy(source)
    changed['tools']['tool_a']['alarms']['a']['cause_text'] = 'Pressure 150 bar'
    assert len(plan_tool_deliveries(modeler_document=_seal(changed),
                                    destination_identities=dest, confirmations=confirm).pending) == 1
    revised = deepcopy(source)
    revised['artifact_ref']['resolution_key']['alarm_configuration_revision'] = 'r2'
    assert len(plan_tool_deliveries(modeler_document=_seal(revised),
                                    destination_identities=dest, confirmations=confirm).pending) == 1


def test_v1_confirmation_forces_v2_migration():
    tool = _tool('tool_a')
    source = _source(tools={'tool_a': tool})
    plan = plan_tool_deliveries(modeler_document=source,
                                destination_identities={'tool_a': 'cosmos-a/db/live'}, confirmations={})
    older = deepcopy(plan.pending[0].confirmation().to_document())
    older['semantic_sha256'] = '0' * 64
    from ada.processes.alarm_delivery.contract import ToolDeliveryConfirmation
    confirm = ToolDeliveryConfirmation.from_document(older)
    assert len(plan_tool_deliveries(modeler_document=source,
                                    destination_identities={'tool_a': 'cosmos-a/db/live'},
                                    confirmations={'tool_a': confirm}).pending) == 1
