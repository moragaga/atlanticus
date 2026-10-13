from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from ada.processes.alarm_modeler.rotation import AlarmRotationError, is_grouped, plan_rotation

_AREAS = ('MINE', 'PLANT')


def _area_members(tool: Mapping[str, object], distributed: list[str]) -> dict[str, list[str]]:
    result = {area: [] for area in _AREAS}
    for occurrence_id in distributed:
        alarm = tool['alarms'][occurrence_id]
        areas = alarm.get('operational_areas')
        if (
            not isinstance(areas, list)
            or not areas
            or any(not isinstance(area, str) or area not in _AREAS for area in areas)
            or len(set(areas)) != len(areas)
        ):
            raise AlarmRotationError('Distributed alarm has invalid operational areas')
        for area in areas:
            result[area].append(occurrence_id)
    return {key: value for key, value in result.items() if value}


def _plan_pool(
    *,
    key: str,
    pool: list[str],
    slots: int,
    state: dict | None,
    previous_visible: list[str],
    now: datetime,
    seconds: float,
) -> tuple[list[str], dict, datetime | None]:
    candidate = {
        'tool_key': key,
        'operator_pool': pool,
        'operator_view': [],
        'meta': {'max_visible_slots': slots},
    }
    previous = {
        'operator_view': [
            {'slot': index, 'occurrence_id': item}
            for index, item in enumerate(previous_visible, start=1)
        ],
    }
    planned, next_state, due = plan_rotation(
        tool=candidate,
        previous_tool=previous,
        state=state,
        now=now,
        rotation_seconds=seconds,
    )
    return [item['occurrence_id'] for item in planned['operator_view']], next_state, due


def plan_distributed_rotation(
    *,
    tool: dict,
    previous_tool: dict | None,
    state: dict | None,
    now: datetime,
    carousel_seconds: float,
    queue_seconds: float,
    slots_per_area: int,
) -> tuple[dict, dict, datetime | None]:
    if not is_grouped(tool):
        raise AlarmRotationError('Distributed Tool must contain a grouped view')
    if (
        type(slots_per_area) is not int
        or slots_per_area < 1
        or type(queue_seconds) not in (int, float)
        or not math.isfinite(queue_seconds)
        or queue_seconds <= 0
    ):
        raise AlarmRotationError('Distributed rotation policy is invalid')
    slots = tool['meta']['max_visible_slots']
    if slots != 6:
        raise AlarmRotationError('Distributed Tool requires six carousel slots')
    grouped_view = [item for item in tool['operator_view'] if 'group' in item]
    if len(grouped_view) != 1 or grouped_view[0]['slot'] != slots:
        raise AlarmRotationError('Distributed Tool group is invalid')
    distributed = grouped_view[0]['group']['occurrence_ids']
    if len(distributed) != len(set(distributed)) or len(distributed) < 2:
        raise AlarmRotationError('Distributed Tool group has invalid membership')
    pool = tool['operator_pool']
    if any(item not in pool for item in distributed):
        raise AlarmRotationError('Distributed Tool group is outside the operator pool')
    normal_pool = [item for item in pool if item not in set(distributed)]
    previous_normal = []
    if previous_tool is not None:
        previous_normal = [
            item['occurrence_id']
            for item in previous_tool['operator_view']
            if 'occurrence_id' in item
        ]
    grouped_state = state if state is not None and set(state) == {'normal', 'areas'} else None
    normal_state = (
        state
        if state is not None and grouped_state is None
        else (None if grouped_state is None else grouped_state['normal'])
    )
    normal_visible, next_normal, normal_due = _plan_pool(
        key=tool['tool_key'],
        pool=normal_pool,
        slots=5,
        state=normal_state,
        previous_visible=previous_normal,
        now=now,
        seconds=carousel_seconds,
    )
    area_pools = _area_members(tool, distributed)
    next_areas = {}
    visible_areas = {}
    deadlines = [normal_due] if normal_due is not None else []
    for area, members in area_pools.items():
        area_state = None if grouped_state is None else grouped_state['areas'].get(area)
        visible, updated, due = _plan_pool(
            key=tool['tool_key'],
            pool=members,
            slots=slots_per_area,
            state=area_state,
            previous_visible=[],
            now=now,
            seconds=queue_seconds,
        )
        visible_areas[area] = visible
        next_areas[area] = updated
        if due is not None:
            deadlines.append(due)
    result = dict(tool)
    result['operator_view'] = [
        {'slot': index, 'occurrence_id': item} for index, item in enumerate(normal_visible, start=1)
    ] + grouped_view
    result['meta'] = {
        **tool['meta'],
        'rotation_pending': len(normal_pool) > 5
        or any(len(members) > slots_per_area for members in area_pools.values()),
        'operator_count': len(result['operator_view']),
        'queue_in_queue': {'slots_per_area': slots_per_area, 'visible_by_area': visible_areas},
    }
    return (
        result,
        {'normal': next_normal, 'areas': next_areas},
        (min(deadlines) if deadlines else None),
    )
