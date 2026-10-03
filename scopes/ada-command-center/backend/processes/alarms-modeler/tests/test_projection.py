from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from ada.contracts.alarms import VisibilityMode
from ada_command_center.processes.alarms_modeler.projection import (
    build_projection_snapshots,
)


def _digest(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()


class _Identity:
    def __init__(self, canonical_key, family_key, alarm_key):
        self.canonical_key = canonical_key
        self.family_key = family_key
        self.alarm_key = alarm_key

    def __hash__(self):
        return hash(self.canonical_key)

    def __eq__(self, other):
        return isinstance(other, _Identity) and other.canonical_key == self.canonical_key


def _target(tool_key):
    return SimpleNamespace(
        tool_key=tool_key,
        component_keys=('main',),
        subcomponents=(),
        process_projection_mode=None,
    )


def _delivery(identity, tool_key):
    enum = lambda value: SimpleNamespace(value=value)
    return SimpleNamespace(
        identity=identity,
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        display_name=identity.alarm_key,
        title=f'Title {identity.alarm_key}',
        cause_template='{value_1}',
        kind=enum('RISK'),
        criticality=enum('C2'),
        business_category=enum('SAFETY_HEALTH'),
        operational_areas=(enum('PLANT'),),
        color=enum('YELLOW'),
        visual_targets=(_target(tool_key),),
    )


def _current(alarms):
    document = {
        'document_type': 'ada_command_center_engine_resolved_current_state',
        'schema_version': 1,
        'artifact_ref': {
            'source_key': 'alarm-configuration',
            'result_id': 'alarm-materialization-' + 'a' * 64,
            'manifest_sha256': 'b' * 64,
            'resolution_key': {
                'alarm_configuration_revision': 'R1',
                'confirmed_tool_catalog_revision': 'T1',
            },
        },
        'state': {
            'resolution_key': {
                'alarm_configuration_revision': 'R1',
                'confirmed_tool_catalog_revision': 'T1',
            },
            'as_of': '2026-10-03T14:37:01Z',
            'alarms': alarms,
        },
    }
    document['sha256'] = _digest(document)
    return document


def _alarm(identity, occurrence, disposition, tool_keys):
    return {
        'identity': identity,
        'occurrence_id': occurrence,
        'episode_id': f'episode-{occurrence}',
        'started_at': '2026-10-03T14:00:00Z',
        'evaluation': {
            'status': 'ACTIVE',
            'evaluated_at': '2026-10-03T14:37:01Z',
            'evidence': {
                'contract_key': 'threshold',
                'contract_version': 'v1',
                'payload': {'value_1': occurrence},
            },
            'error': None,
        },
        'priority': {'disposition': disposition, 'blockers': []},
        'technical_hold': None,
        'management_cycle': None,
        'management_effect': None,
        'deactivation_effect': None,
        'pending_deactivation_request': None,
        'assignments': [
            {'tool_key': tool_key, 'assigned_at': '2026-10-03T14:00:00Z'}
            for tool_key in tool_keys
        ],
        'pending_assignments': [],
    }


def test_only_predominant_occurrences_enter_pool_and_escalated_destination_is_projected():
    a = _Identity('family/a', 'family', 'a')
    b = _Identity('family/b', 'family', 'b')
    c = _Identity('other/c', 'other', 'c')
    key = SimpleNamespace(
        alarm_configuration_revision='R1',
        confirmed_tool_catalog_revision='T1',
    )
    runtime = SimpleNamespace(
        resolution_key=key,
        planned_alarms=(
            SimpleNamespace(identity=a, priority_order=1),
            SimpleNamespace(identity=b, priority_order=2),
            SimpleNamespace(identity=c, priority_order=1),
        ),
    )
    delivery_a = _delivery(a, 'tool-a')
    delivery_a.visual_targets = (_target('tool-a'), _target('tool-b'))
    delivery = SimpleNamespace(
        resolution_key=key,
        alarms=(
            delivery_a,
            _delivery(b, 'tool-a'),
            _delivery(c, 'tool-a'),
        ),
    )

    snapshots = build_projection_snapshots(
        current_document=_current(
            [
                _alarm('family/a', 'occ-a', 'PREDOMINANT', ['tool-a', 'tool-b']),
                _alarm('family/b', 'occ-b', 'ECLIPSED', ['tool-a']),
                _alarm('other/c', 'occ-c', 'PREDOMINANT', ['tool-a']),
            ]
        ),
        runtime_configuration=runtime,
        delivery_configuration=delivery,
    )
    by_tool = {item['tool_key']: item for item in snapshots}
    assert by_tool['tool-a']['operator_pool'] == ['occ-a', 'occ-c']
    assert 'occ-b' not in by_tool['tool-a']['alarms']
    assert by_tool['tool-b']['operator_pool'] == ['occ-a']
    assert by_tool['tool-a']['operator_view'][0] == {
        'slot': 1,
        'occurrence_id': 'occ-a',
    }
