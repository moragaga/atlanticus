from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

LIVE_PUBLIC_SCHEMA_VERSION = 2

_ALARM_FIELDS = (
    'alarm_identity',
    'family_key',
    'alarm_key',
    'occurrence_id',
    'episode_id',
    'started_at',
    'display_name',
    'title',
    'cause_text',
    'kind',
    'criticality',
    'business_category',
    'operational_areas',
    'color',
    'visual_target',
    'messages',
    'default_deactivation_policy',
    'management_cycle',
    'directly_managed',
    'attention_required',
)


class AlarmLiveProjectionError(ValueError):
    pass


def public_tool_projection(tool: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(tool, Mapping):
        raise AlarmLiveProjectionError('Live Tool must be a mapping')
    raw_alarms = tool.get('alarms')
    raw_view = tool.get('operator_view')
    meta = tool.get('meta')
    if (
        not isinstance(raw_alarms, dict)
        or not isinstance(raw_view, list)
        or not isinstance(meta, dict)
    ):
        raise AlarmLiveProjectionError('Live Tool content is invalid')
    if not isinstance(tool.get('retired'), bool):
        raise AlarmLiveProjectionError('Live Tool retired flag is invalid')
    alarms: dict[str, dict[str, object]] = {}
    for occurrence_id, record in raw_alarms.items():
        if (
            not isinstance(occurrence_id, str)
            or not occurrence_id
            or not isinstance(record, Mapping)
        ):
            raise AlarmLiveProjectionError('Live alarm record is invalid')
        alarms[occurrence_id] = {
            name: deepcopy(record[name]) for name in _ALARM_FIELDS if name in record
        }
    view: list[dict[str, object]] = []
    for item in raw_view:
        if not isinstance(item, dict) or 'slot' not in item:
            raise AlarmLiveProjectionError('Live operator slot is invalid')
        if 'group' not in item:
            view.append(deepcopy(item))
            continue
        group = item['group']
        if not isinstance(group, dict) or group.get('kind') != 'DISTRIBUTED':
            raise AlarmLiveProjectionError('Live distributed group is invalid')
        members = group.get('occurrence_ids')
        queue = meta.get('queue_in_queue')
        if not isinstance(members, list) or not isinstance(queue, dict):
            raise AlarmLiveProjectionError('Live distributed selection is missing')
        visible = queue.get('visible_by_area')
        slots = queue.get('slots_per_area')
        if not isinstance(visible, dict) or type(slots) is not int or slots <= 0:
            raise AlarmLiveProjectionError('Live distributed selection is invalid')
        totals: dict[str, int] = {}
        for member in members:
            if member not in alarms:
                raise AlarmLiveProjectionError('Live distributed member is unknown')
            for area in raw_alarms[member].get('operational_areas', []):
                totals[area] = totals.get(area, 0) + 1
        for area, selected in visible.items():
            if (
                area not in totals
                or not isinstance(selected, list)
                or len(selected) > slots
                or len(selected) != len(set(selected))
                or any(
                    member not in members
                    or area not in raw_alarms[member].get('operational_areas', [])
                    for member in selected
                )
            ):
                raise AlarmLiveProjectionError('Live distributed area selection is invalid')
        view.append(
            {
                'slot': item['slot'],
                'group': {
                    'kind': 'DISTRIBUTED',
                    'visible_by_area': deepcopy(visible),
                    'total_by_area': totals,
                },
            }
        )
    return {
        'retired': tool['retired'],
        'alarms': alarms,
        'operator_view': view,
        'max_visible_slots': meta.get('max_visible_slots'),
        'counts': {
            'live': meta.get('live_count'),
            'attention': meta.get('attention_count'),
        },
    }
