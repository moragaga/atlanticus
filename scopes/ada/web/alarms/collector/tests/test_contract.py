from copy import deepcopy

import pytest

from ada.web.alarms.collector.contracts import (
    AlarmLiveContractError,
    validate_live_document,
)


def alarm(key: str, areas=None) -> dict:
    return {
        'occurrence_id': key, 'alarm_identity': f'family/{key}',
        'title': f'Alarm {key}', 'cause_text': 'Pressure 120',
        'directly_managed': False, 'attention_required': True,
        'operational_areas': ['MINE'] if areas is None else areas,
    }


def live(key='tool-a', *, count=0) -> dict:
    alarms = {f'occ-{i}': alarm(f'occ-{i}') for i in range(count)}
    return {
        'id': f'alarm-live:{key}',
        'document_type': 'ada_alarm_live_tool_projection',
        'schema_version': 2,
        'tool_key': key,
        'retired': False,
        'alarms': alarms,
        'operator_view': [
            {'slot': i + 1, 'occurrence_id': f'occ-{i}'} for i in range(count)
        ],
        'max_visible_slots': 6,
        'counts': {'live': count, 'attention': count},
        'resolution_key': {
            'alarm_configuration_revision': 'R1',
            'confirmed_tool_catalog_revision': 'T1',
        },
        'source_as_of': '2026-10-11T20:00:00Z',
        'source_sha256': 'a' * 64,
        'semantic_sha256': 'b' * 64,
    }


def test_valid_empty_live_is_not_missing() -> None:
    doc = live()
    result = validate_live_document(doc, tool_key='tool-a')
    assert result['alarms'] == {}
    result['counts']['attention'] = 5
    assert doc['counts']['attention'] == 0


def test_invalid_tool_identity_or_version_is_rejected() -> None:
    with pytest.raises(AlarmLiveContractError, match='identity'):
        validate_live_document(live(), tool_key='tool-b')
    item = live()
    item['schema_version'] = 1
    with pytest.raises(AlarmLiveContractError, match='version'):
        validate_live_document(item, tool_key='tool-a')


def test_invalid_view_cannot_leak_other_occurrences() -> None:
    doc = live(count=1)
    doc['operator_view'].append({'slot': 2, 'occurrence_id': 'foreign'})
    with pytest.raises(AlarmLiveContractError, match='unknown'):
        validate_live_document(doc, tool_key='tool-a')
    doc = live(count=1)
    doc['operator_view'].append({'slot': 1, 'occurrence_id': 'occ-0'})
    with pytest.raises(AlarmLiveContractError, match='slots'):
        validate_live_document(doc, tool_key='tool-a')


def test_distributed_selection_keeps_per_area_memberships() -> None:
    doc = live(count=0)
    doc['alarms'] = {
        'a': alarm('a', ['MINE']),
        'b': alarm('b', ['MINE', 'PLANT']),
        'c': alarm('c', ['PLANT']),
        'd': alarm('d', ['MINE']),
    }
    doc['counts'] = {'live': 4, 'attention': 4}
    doc['operator_view'] = [
        {'slot': 6, 'group': {'kind': 'DISTRIBUTED',
                             'visible_by_area': {'MINE': ['a', 'b'], 'PLANT': ['b', 'c']},
                             'total_by_area': {'MINE': 3, 'PLANT': 2}}}
    ]
    assert validate_live_document(doc, tool_key='tool-a')['operator_view'] == doc['operator_view']
    wrong = deepcopy(doc)
    wrong['operator_view'][0]['group']['visible_by_area']['PLANT'] = ['a']
    with pytest.raises(AlarmLiveContractError, match='invalid area'):
        validate_live_document(wrong, tool_key='tool-a')


def test_retired_tool_requires_empty_live_state() -> None:
    doc = live(count=1)
    doc['retired'] = True
    with pytest.raises(AlarmLiveContractError, match='empty'):
        validate_live_document(doc, tool_key='tool-a')
    doc = live()
    doc['retired'] = True
    assert validate_live_document(doc, tool_key='tool-a')['retired'] is True
