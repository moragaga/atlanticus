# Define y valida el contrato físico Live v2 sin depender del engine ni de Delivery.
from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta

LIVE_CONTAINER = 'alarm-live-projection'
LIVE_DOCUMENT_TYPE = 'ada_alarm_live_tool_projection'
LIVE_SCHEMA_VERSION = 2
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_FIELDS = frozenset({
    'id', 'document_type', 'schema_version', 'tool_key', 'retired', 'alarms',
    'operator_view', 'max_visible_slots', 'counts', 'resolution_key',
    'source_as_of', 'source_sha256', 'semantic_sha256',
})
_ALARM_FIELDS = frozenset({
    'alarm_identity', 'family_key', 'alarm_key', 'occurrence_id', 'episode_id',
    'started_at', 'display_name', 'title', 'cause_text', 'kind', 'criticality',
    'business_category', 'operational_areas', 'color', 'visual_target', 'messages',
    'default_deactivation_policy', 'management_cycle', 'directly_managed',
    'attention_required',
})
_RESOLUTION_FIELDS = frozenset({
    'alarm_configuration_revision', 'confirmed_tool_catalog_revision',
})


# Agrupa una responsabilidad operativa y sus invariantes.
class AlarmLiveContractError(ValueError):
    pass


# Valida y transforma datos en una frontera contractual verificable.
def required_key(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AlarmLiveContractError(f'{name} must be normalized text')
    return value


# Valida y transforma datos en una frontera contractual verificable.
def _mapping(value: object, name: str, keys: frozenset[str] | None = None) -> Mapping:
    if not isinstance(value, Mapping) or (keys is not None and set(value) != keys):
        raise AlarmLiveContractError(f'{name} has invalid fields')
    return value


# Valida y transforma datos en una frontera contractual verificable.
def _utc(value: object, name: str) -> None:
    required_key(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AlarmLiveContractError(f'{name} is invalid') from error
    if parsed.utcoffset() != timedelta(0):
        raise AlarmLiveContractError(f'{name} must be UTC')


# Valida y transforma datos en una frontera contractual verificable.
def _alarm(occurrence_id: str, value: object) -> None:
    record = _mapping(value, 'alarm')
    if not set(record).issubset(_ALARM_FIELDS) or record.get('occurrence_id') != occurrence_id:
        raise AlarmLiveContractError('Alarm occurrence identity or fields are invalid')
    for name in ('alarm_identity', 'title'):
        required_key(record.get(name), name)
    if not isinstance(record.get('cause_text'), str):
        raise AlarmLiveContractError('Alarm cause_text must be text')
    for name in ('directly_managed', 'attention_required'):
        if type(record.get(name)) is not bool:
            raise AlarmLiveContractError(f'Alarm {name} is invalid')
    areas = record.get('operational_areas')
    if not isinstance(areas, list) or any(not isinstance(x, str) for x in areas):
        raise AlarmLiveContractError('Alarm operational areas are invalid')
    if len(areas) != len(set(areas)):
        raise AlarmLiveContractError('Alarm operational areas are duplicated')


# Valida y transforma datos en una frontera contractual verificable.
def _view(value: object, alarms: Mapping, max_slots: int) -> None:
    if not isinstance(value, list):
        raise AlarmLiveContractError('Live operator view must be a list')
    seen_slots: set[int] = set()
    seen_occurrences: set[str] = set()
    groups = 0
    for entry in value:
        item = _mapping(entry, 'operator slot')
        slot = item.get('slot')
        if type(slot) is not int or not 1 <= slot <= max_slots or slot in seen_slots:
            raise AlarmLiveContractError('Live operator slots are invalid')
        seen_slots.add(slot)
        if set(item) == {'slot', 'occurrence_id'}:
            occurrence_id = required_key(item['occurrence_id'], 'visible occurrence')
            if occurrence_id not in alarms or occurrence_id in seen_occurrences:
                raise AlarmLiveContractError('Visible occurrence is unknown or duplicated')
            seen_occurrences.add(occurrence_id)
        elif set(item) == {'slot', 'group'}:
            groups += 1
            if groups > 1 or slot != max_slots or max_slots != 6:
                raise AlarmLiveContractError('Distributed group occupies an invalid slot')
            group = _mapping(item['group'], 'distributed group', frozenset({
                'kind', 'visible_by_area', 'total_by_area',
            }))
            if group['kind'] != 'DISTRIBUTED':
                raise AlarmLiveContractError('Unsupported distributed group')
            visible = _mapping(group['visible_by_area'], 'visible_by_area')
            totals = _mapping(group['total_by_area'], 'total_by_area')
            if not visible or set(visible) != set(totals):
                raise AlarmLiveContractError('Distributed areas are inconsistent')
            for area, selected in visible.items():
                required_key(area, 'area')
                count = totals[area]
                if type(count) is not int or count < 1:
                    raise AlarmLiveContractError('Distributed area total is invalid')
                if (
                    not isinstance(selected, list) or len(selected) > 3
                    or len(selected) > count or len(selected) != len(set(selected))
                ):
                    raise AlarmLiveContractError('Distributed area selection is invalid')
                for occurrence_id in selected:
                    if (
                        not isinstance(occurrence_id, str)
                        or occurrence_id not in alarms
                        or area not in alarms[occurrence_id]['operational_areas']
                    ):
                        raise AlarmLiveContractError('Distributed occurrence has invalid area')
        else:
            raise AlarmLiveContractError('Live operator slot shape is invalid')


# Valida y transforma datos en una frontera contractual verificable.
def validate_live_document(document: object, *, tool_key: str) -> dict:
    key = required_key(tool_key, 'tool_key')
    value = _mapping(document, 'Live document', _FIELDS)
    if (
        value['id'] != f'alarm-live:{key}'
        or value['tool_key'] != key
        or value['document_type'] != LIVE_DOCUMENT_TYPE
        or type(value['schema_version']) is not int
        or value['schema_version'] != LIVE_SCHEMA_VERSION
    ):
        raise AlarmLiveContractError('Live document identity or version is invalid')
    if type(value['retired']) is not bool:
        raise AlarmLiveContractError('Live retired flag is invalid')
    for name in ('source_sha256', 'semantic_sha256'):
        if not isinstance(value[name], str) or _SHA.fullmatch(value[name]) is None:
            raise AlarmLiveContractError(f'{name} is not a SHA-256 digest')
    _utc(value['source_as_of'], 'source_as_of')
    resolution = _mapping(value['resolution_key'], 'resolution_key', _RESOLUTION_FIELDS)
    for name in _RESOLUTION_FIELDS:
        required_key(resolution[name], name)
    alarms = _mapping(value['alarms'], 'alarms')
    for occurrence_id, alarm in alarms.items():
        required_key(occurrence_id, 'occurrence_id')
        _alarm(occurrence_id, alarm)
    max_slots = value['max_visible_slots']
    if type(max_slots) is not int or max_slots < 1:
        raise AlarmLiveContractError('max_visible_slots is invalid')
    _view(value['operator_view'], alarms, max_slots)
    counts = _mapping(value['counts'], 'counts', frozenset({'live', 'attention'}))
    if any(type(item) is not int or item < 0 for item in counts.values()):
        raise AlarmLiveContractError('Live counts are invalid')
    if counts['live'] != len(alarms) or counts['attention'] < len(value['operator_view']):
        raise AlarmLiveContractError('Live counts disagree with the projection')
    if value['retired'] and (alarms or value['operator_view'] or counts['attention']):
        raise AlarmLiveContractError('Retired Tool must have an empty Live state')
    return deepcopy(dict(value))
