from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from ada.processes.alarm_modeler.distributed_rotation import plan_distributed_rotation
from ada.processes.alarm_modeler.rotation import AlarmRotationError, ToolRotationMemory


START = datetime(2026, 10, 11, tzinfo=UTC)


def _at(seconds: int):
    return START + timedelta(seconds=seconds)


def _tool(key='integrated', *, normals=6, mine=5, plant=4, multiarea=False):
    n = [f'n{i}' for i in range(normals)]
    m = [f'm{i}' for i in range(mine)]
    p = [f'p{i}' for i in range(plant)]
    if multiarea:
        m.append('both')
    all_ids = n + m + p
    alarms = {
        item: {'operational_areas': ['MINE'] if item in m else ['PLANT']}
        for item in all_ids
    }
    if multiarea:
        alarms['both']['operational_areas'] = ['MINE','PLANT']
    return {
        'tool_key': key, 'retired': False, 'alarms': alarms,
        'operator_pool': all_ids,
        'operator_view': [
            {'slot': 6, 'group': {'kind': 'DISTRIBUTED', 'occurrence_ids': m + p}}
        ],
        'meta': {'max_visible_slots': 6, 'operator_count': 1, 'rotation_pending': True},
    }


def _plan(tool, previous=None, state=None, seconds=0):
    return plan_distributed_rotation(
        tool=tool, previous_tool=previous, state=state, now=_at(seconds),
        carousel_seconds=90, queue_seconds=120, slots_per_area=3,
    )


def _areas(tool):
    return tool['meta']['queue_in_queue']['visible_by_area']


def test_normal_and_area_deadlines_are_independent():
    raw = _tool()
    first,state,deadline=_plan(raw)
    assert deadline == _at(90)
    assert [item['occurrence_id'] for item in first['operator_view'][:-1]] == ['n0','n1','n2','n3','n4']
    assert _areas(first)['MINE'] == ['m0','m1','m2']
    assert _areas(first)['PLANT'] == ['p0','p1','p2']
    second,state,deadline=_plan(raw,first,state,90)
    assert deadline == _at(120)
    assert [item['occurrence_id'] for item in second['operator_view'][:-1]] == ['n5','n0','n1','n2','n3']
    assert _areas(second)==_areas(first)
    third,state,deadline=_plan(raw,second,state,120)
    assert _areas(third)['MINE'] == ['m3','m4','m0']
    assert _areas(third)['PLANT'] == ['p3','p0','p1']
    assert deadline == _at(180)


def test_no_starvation_with_new_distributed_arrivals():
    raw = _tool(normals=0,mine=5,plant=0)
    first,state,_=_plan(raw)
    raw2=deepcopy(raw)
    raw2['alarms']['new']={'operational_areas':['MINE']}
    raw2['operator_pool'].insert(0,'new')
    raw2['operator_view'][0]['group']['occurrence_ids'].insert(0,'new')
    before,state,_=_plan(raw2,first,state,119)
    assert _areas(before)['MINE'] == ['m0','m1','m2']
    after,state,_=_plan(raw2,before,state,120)
    assert _areas(after)['MINE'] == ['m3','m4','new']


def test_multiarea_occurrence_is_one_record_with_two_area_references():
    raw=_tool(normals=0,mine=2,plant=2,multiarea=True)
    result,_,deadline=_plan(raw)
    assert 'both' in _areas(result)['MINE']
    assert 'both' in _areas(result)['PLANT']
    assert len(result['alarms']) == len(raw['alarms'])
    assert deadline is None


def test_empty_area_is_not_projected_and_no_deadline_for_small_queues():
    raw=_tool(normals=0,mine=2,plant=0)
    result,_,deadline=_plan(raw)
    assert _areas(result) == {'MINE':['m0','m1']}
    assert deadline is None
    assert result['meta']['rotation_pending'] is False


def test_malformed_area_is_rejected():
    raw=_tool(normals=0,mine=2,plant=0)
    raw['alarms']['m0']['operational_areas']=['MINE','UNDERGROUND']
    with pytest.raises(AlarmRotationError,match='operational areas'):
        _plan(raw)


def test_memory_recovers_group_and_next_rotation_after_restart(tmp_path):
    raw=_tool()
    memory=ToolRotationMemory(tmp_path)
    first,state,_=_plan(raw)
    memory.prepare(tool_key=raw['tool_key'],previous_tool=None,old_state=None,next_tool=first,next_state=state)
    memory.confirm(tool_key=raw['tool_key'],current_tool=first)
    restarted=ToolRotationMemory(tmp_path)
    previous_state=restarted.read(tool_key=raw['tool_key'],previous_tool=first)
    assert previous_state==state
    second,second_state,_=_plan(raw,first,previous_state,120)
    assert _areas(second)!=_areas(first)
    restarted.prepare(tool_key=raw['tool_key'],previous_tool=first,old_state=state,next_tool=second,next_state=second_state)
    assert restarted.read(tool_key=raw['tool_key'],previous_tool=first)==state
    assert restarted.read(tool_key=raw['tool_key'],previous_tool=second)==second_state


def test_distinct_tool_memories_remain_isolated(tmp_path):
    memory=ToolRotationMemory(tmp_path)
    for key in ('integrated-ops','process-other'):
        raw=_tool(key)
        tool,state,_=_plan(raw)
        memory.prepare(tool_key=key,previous_tool=None,old_state=None,next_tool=tool,next_state=state)
        memory.confirm(tool_key=key,current_tool=tool)
    assert len(list((tmp_path/'state'/'rotation').glob('*.json')))==2


def test_transition_from_plain_state_is_possible():
    raw=_tool(normals=6,mine=4,plant=2)
    from ada.processes.alarm_modeler.rotation import plan_rotation
    generic={'tool_key':'integrated','operator_pool':['n0','n1','n2','n3','n4','n5'],
             'meta':{'max_visible_slots':6},'operator_view':[]}
    _,initial,_=plan_rotation(tool=generic,previous_tool=None,state=None,now=_at(0),rotation_seconds=90)
    result,states,due=_plan(raw,state=initial)
    assert len(result['operator_view'])==6
    assert states['normal']['visible']==['n0','n1','n2','n3','n4']
    assert due == _at(90)


def test_stale_group_memory_must_not_silently_reset(tmp_path):
    mem=ToolRotationMemory(tmp_path)
    raw=_tool()
    first,state,_=_plan(raw)
    mem.prepare(tool_key=raw['tool_key'],previous_tool=None,old_state=None,next_tool=first,next_state=state)
    mem.confirm(tool_key=raw['tool_key'],current_tool=first)
    tampered=deepcopy(first)
    tampered['meta']['queue_in_queue']['visible_by_area']['MINE']=['m3','m4']
    with pytest.raises(AlarmRotationError, match='disagrees'):
        mem.read(tool_key=raw['tool_key'],previous_tool=tampered)
