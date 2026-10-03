# Espejo pedagógico en español del archivo productivo equivalente.
# Mantiene exactamente el mismo comportamiento; los comentarios explican la intención.
# Este incremento prioriza el flujo vertical Runtime -> Modeler -> Delivery -> Cosmos.

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from ada.contracts.alarms import VisibilityMode
from ada_command_center.alarms.materialization import (
    DeliveryAlarmConfiguration,
    RuntimeAlarmConfiguration,
)

DOCUMENT_TYPE = 'ada_alarm_projection_snapshot'
SCHEMA_VERSION = 1
INDEX_DOCUMENT_TYPE = 'ada_alarm_modeler_projection_index'
MAX_VISIBLE_SLOTS = 6


class AlarmProjectionError(ValueError):
    pass


def document_digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(document),
            sort_keys=True,
            ensure_ascii=False,
            separators=(',', ':'),
        ).encode('utf-8')
    ).hexdigest()


def with_digest(document: Mapping[str, object]) -> dict[str, object]:
    value = dict(document)
    value['sha256'] = document_digest(value)
    return value


def build_projection_snapshots(
    *,
    current_document: Mapping[str, object],
    runtime_configuration: RuntimeAlarmConfiguration,
    delivery_configuration: DeliveryAlarmConfiguration,
    max_visible_slots: int = MAX_VISIBLE_SLOTS,
) -> tuple[dict[str, object], ...]:
    if isinstance(max_visible_slots, bool) or not isinstance(max_visible_slots, int):
        raise TypeError('max_visible_slots must be an int')
    if max_visible_slots <= 0:
        raise ValueError('max_visible_slots must be positive')
    state = _current_state(current_document)
    if runtime_configuration.resolution_key != delivery_configuration.resolution_key:
        raise AlarmProjectionError('Runtime and projection configurations must share resolution_key')
    expected_resolution = {
        'alarm_configuration_revision': runtime_configuration.resolution_key.alarm_configuration_revision,
        'confirmed_tool_catalog_revision': (
            runtime_configuration.resolution_key.confirmed_tool_catalog_revision
        ),
    }
    if state['resolution_key'] != expected_resolution:
        raise AlarmProjectionError('Runtime current state does not match modeler configuration')
    runtime_by_identity = {
        alarm.identity.canonical_key: alarm for alarm in runtime_configuration.planned_alarms
    }
    delivery_by_identity = {
        alarm.identity.canonical_key: alarm for alarm in delivery_configuration.alarms
    }
    tool_keys = tuple(
        sorted(
            {
                target.tool_key
                for alarm in delivery_configuration.alarms
                if alarm.is_active and alarm.visibility_mode is VisibilityMode.VISIBLE
                for target in alarm.visual_targets
            }
        )
    )
    candidates: dict[str, list[dict[str, object]]] = {tool_key: [] for tool_key in tool_keys}
    for current in state['alarms']:
        if current['evaluation']['status'] != 'ACTIVE':
            continue
        if current['priority']['disposition'] != 'PREDOMINANT':
            continue
        identity = current['identity']
        runtime_alarm = runtime_by_identity.get(identity)
        delivery_alarm = delivery_by_identity.get(identity)
        if runtime_alarm is None or delivery_alarm is None:
            raise AlarmProjectionError(f'Runtime current alarm is not materialized: {identity}')
        if not delivery_alarm.is_active or delivery_alarm.visibility_mode is not VisibilityMode.VISIBLE:
            continue
        assigned = {item['tool_key'] for item in current['assignments']}
        targets = {target.tool_key: target for target in delivery_alarm.visual_targets}
        for tool_key in sorted(assigned & targets.keys()):
            target = targets[tool_key]
            evidence = current['evaluation']['evidence']
            candidates.setdefault(tool_key, []).append(
                {
                    'alarm_identity': identity,
                    'alarm_key': delivery_alarm.identity.alarm_key,
                    'family_key': delivery_alarm.identity.family_key,
                    'occurrence_id': current['occurrence_id'],
                    'episode_id': current['episode_id'],
                    'priority_order': runtime_alarm.priority_order,
                    'started_at': current['started_at'],
                    'last_seen_at': state['as_of'],
                    'display_name': delivery_alarm.display_name,
                    'title': delivery_alarm.title,
                    'cause_template': delivery_alarm.cause_template,
                    'kind': delivery_alarm.kind.value,
                    'criticality': delivery_alarm.criticality.value,
                    'business_category': delivery_alarm.business_category.value,
                    'operational_areas': [item.value for item in delivery_alarm.operational_areas],
                    'color': delivery_alarm.color.value,
                    'evidence': evidence,
                    'visual_target': {
                        'component_keys': list(target.component_keys),
                        'subcomponents': [
                            {
                                'owner_component_key': item.owner_component_key,
                                'subcomponent_key': item.subcomponent_key,
                            }
                            for item in target.subcomponents
                        ],
                        'process_projection_mode': (
                            None
                            if target.process_projection_mode is None
                            else target.process_projection_mode.value
                        ),
                    },
                }
            )
    return tuple(
        _snapshot(
            tool_key=tool_key,
            rows=candidates.get(tool_key, []),
            current_document=current_document,
            as_of=state['as_of'],
            max_visible_slots=max_visible_slots,
        )
        for tool_key in tool_keys
    )


def build_projection_index(
    *,
    artifact_ref: Mapping[str, object],
    snapshot_timestamp: str,
    snapshots: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    entries = []
    for snapshot in snapshots:
        tool_key = snapshot.get('tool_key')
        digest = snapshot.get('sha256')
        if not isinstance(tool_key, str) or not tool_key:
            raise AlarmProjectionError('Projection snapshot tool_key is invalid')
        if not isinstance(digest, str) or len(digest) != 64:
            raise AlarmProjectionError('Projection snapshot checksum is invalid')
        entries.append(
            {
                'tool_key': tool_key,
                'path': projection_path(tool_key),
                'sha256': digest,
            }
        )
    return with_digest(
        {
            'document_type': INDEX_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'artifact_ref': dict(artifact_ref),
            'snapshot_timestamp': snapshot_timestamp,
            'snapshots': entries,
        }
    )


def projection_path(tool_key: str) -> str:
    if not isinstance(tool_key, str) or not tool_key or tool_key != tool_key.strip():
        raise ValueError('tool_key must be non-empty text')
    digest = hashlib.sha256(tool_key.encode('utf-8')).hexdigest()
    return f'current/tools/{digest}/latest.json'


def _snapshot(
    *,
    tool_key: str,
    rows: list[dict[str, object]],
    current_document: Mapping[str, object],
    as_of: str,
    max_visible_slots: int,
) -> dict[str, object]:
    ordered = sorted(
        rows,
        key=lambda item: (
            item['priority_order'],
            item['started_at'],
            item['alarm_identity'],
            item['occurrence_id'],
        ),
    )
    alarms = {item['occurrence_id']: item for item in ordered}
    pool = [item['occurrence_id'] for item in ordered]
    visible = pool[:max_visible_slots]
    tool_digest = hashlib.sha256(tool_key.encode('utf-8')).hexdigest()[:16]
    return with_digest(
        {
            'id': f'alarm_projection_snapshot:{tool_digest}',
            'document_type': DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'artifact_ref': dict(current_document['artifact_ref']),
            'snapshot_timestamp': as_of,
            'tool_key': tool_key,
            'alarms': alarms,
            'operator_pool': pool,
            'operator_view': [
                {'slot': index, 'occurrence_id': occurrence_id}
                for index, occurrence_id in enumerate(visible, start=1)
            ],
            'meta': {
                'operator_count': len(visible),
                'operator_pool_count': len(pool),
                'total_count': len(pool),
                'max_visible_slots': max_visible_slots,
            },
        }
    )


def _current_state(document: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise TypeError('current_document must be a mapping')
    if document.get('document_type') != 'ada_command_center_engine_resolved_current_state':
        raise AlarmProjectionError('Runtime current document type is unsupported')
    if document.get('schema_version') != 1:
        raise AlarmProjectionError('Runtime current schema version is unsupported')
    expected_digest = document.get('sha256')
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise AlarmProjectionError('Runtime current checksum is invalid')
    payload = {key: value for key, value in document.items() if key != 'sha256'}
    if document_digest(payload) != expected_digest:
        raise AlarmProjectionError('Runtime current checksum mismatch')
    artifact_ref = document.get('artifact_ref')
    state = document.get('state')
    if not isinstance(artifact_ref, Mapping) or not isinstance(state, Mapping):
        raise AlarmProjectionError('Runtime current document is incomplete')
    if set(state) != {'resolution_key', 'as_of', 'alarms'}:
        raise AlarmProjectionError('Runtime current state has unsupported fields')
    if not isinstance(state['as_of'], str) or not state['as_of']:
        raise AlarmProjectionError('Runtime current timestamp is invalid')
    if not isinstance(state['alarms'], list):
        raise AlarmProjectionError('Runtime current alarms must be an array')
    for alarm in state['alarms']:
        _validate_current_alarm(alarm)
    return dict(state)


def _validate_current_alarm(alarm: object) -> None:
    if not isinstance(alarm, Mapping):
        raise AlarmProjectionError('Runtime current alarm must be an object')
    required = {
        'identity',
        'occurrence_id',
        'episode_id',
        'started_at',
        'evaluation',
        'priority',
        'assignments',
    }
    if not required <= set(alarm):
        raise AlarmProjectionError('Runtime current alarm is incomplete')
    for key in ('identity', 'occurrence_id', 'episode_id', 'started_at'):
        if not isinstance(alarm[key], str) or not alarm[key]:
            raise AlarmProjectionError(f'Runtime current {key} is invalid')
    evaluation = alarm['evaluation']
    priority = alarm['priority']
    assignments = alarm['assignments']
    if not isinstance(evaluation, Mapping) or evaluation.get('status') not in {
        'ACTIVE',
        'INACTIVE',
        'ERROR',
    }:
        raise AlarmProjectionError('Runtime current evaluation is invalid')
    if not isinstance(priority, Mapping) or priority.get('disposition') not in {
        'PREDOMINANT',
        'DEACTIVATED',
        'ECLIPSED',
        'CASCADE_SUPPRESSED',
    }:
        raise AlarmProjectionError('Runtime current priority is invalid')
    if not isinstance(assignments, list):
        raise AlarmProjectionError('Runtime current assignments must be an array')
    for assignment in assignments:
        if (
            not isinstance(assignment, Mapping)
            or not isinstance(assignment.get('tool_key'), str)
            or not assignment['tool_key']
        ):
            raise AlarmProjectionError('Runtime current assignment is invalid')
