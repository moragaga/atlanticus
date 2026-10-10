# Transforma estado operacional validado a vistas vivas y selección de atención por herramienta.
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime

DOCUMENT_TYPE = 'ada_alarm_modeler_live_projection'
SCHEMA_VERSION = 1
SOURCE_DOCUMENT_TYPE = 'ada_alarm_engine_resolved_current_state'


# Responsabilidad de AlarmModelerProjectionError: ejecutar el contrato local sin efectos implícitos.
class AlarmModelerProjectionError(ValueError):
    pass


# Responsabilidad de digest: ejecutar el contrato local sin efectos implícitos.
def digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            document,
            sort_keys=True,
            ensure_ascii=False,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    ).hexdigest()


# Verifica estructura y SHA-256 antes de consumir o reutilizar un documento.
def validate_document(document: object, *, source: bool = False) -> dict:
    expected_type = SOURCE_DOCUMENT_TYPE if source else DOCUMENT_TYPE
    fields = (
        {'document_type', 'schema_version', 'artifact_ref', 'journal_position', 'state', 'sha256'}
        if source
        else {
            'document_type', 'schema_version', 'artifact_ref', 'source_journal_position',
            'source_as_of', 'tools', 'sha256',
        }
    )
    if not isinstance(document, dict) or set(document) != fields:
        raise AlarmModelerProjectionError('Projection document has invalid fields')
    if document['document_type'] != expected_type or document['schema_version'] != SCHEMA_VERSION:
        raise AlarmModelerProjectionError('Projection document has invalid contract version')
    checksum = document['sha256']
    if not isinstance(checksum, str) or checksum != digest(
        {key: value for key, value in document.items() if key != 'sha256'}
    ):
        raise AlarmModelerProjectionError('Projection document checksum mismatch')
    if not isinstance(document['artifact_ref'], dict):
        raise AlarmModelerProjectionError('Projection artifact reference is invalid')
    if source:
        state = document['state']
        if not isinstance(state, dict) or set(state) != {'resolution_key', 'as_of', 'alarms'}:
            raise AlarmModelerProjectionError('Resolved CURRENT state is invalid')
        if state['resolution_key'] != document['artifact_ref'].get('resolution_key'):
            raise AlarmModelerProjectionError('Resolved CURRENT revisions differ')
        if not isinstance(state['alarms'], list) or not isinstance(state['as_of'], str):
            raise AlarmModelerProjectionError('Resolved CURRENT contents are invalid')
        if not isinstance(document['journal_position'], dict):
            raise AlarmModelerProjectionError('Resolved CURRENT position is invalid')
    else:
        if not isinstance(document['tools'], dict):
            raise AlarmModelerProjectionError('Modeler tool inventory is invalid')
        if not isinstance(document['source_journal_position'], dict):
            raise AlarmModelerProjectionError('Modeler journal position is invalid')
        if not isinstance(document['source_as_of'], str):
            raise AlarmModelerProjectionError('Modeler source timestamp is invalid')
        for tool_key, value in document['tools'].items():
            if not isinstance(tool_key, str) or not isinstance(value, dict):
                raise AlarmModelerProjectionError('Modeler tool projection is invalid')
            if set(value) != {
                'tool_key', 'retired', 'alarms', 'operator_pool', 'operator_view', 'meta'
            } or value['tool_key'] != tool_key or not isinstance(value['retired'], bool):
                raise AlarmModelerProjectionError('Modeler tool projection is invalid')
            if not isinstance(value['alarms'], dict) or not isinstance(value['operator_pool'], list):
                raise AlarmModelerProjectionError('Modeler tool content is invalid')
            if not isinstance(value['operator_view'], list) or not isinstance(value['meta'], dict):
                raise AlarmModelerProjectionError('Modeler tool view is invalid')
            if value['retired'] and (value['alarms'] or value['operator_pool'] or value['operator_view']):
                raise AlarmModelerProjectionError('Retired tool projection must be empty')
    return document


# Responsabilidad de _required_text: ejecutar el contrato local sin efectos implícitos.
def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AlarmModelerProjectionError(f'{label} must be non-empty normalized text')
    return value


# Separa alarmas vivas de espacios de atención y aplica rotación determinista.
def _tool_projection(tool_key: str, alarms: list[dict], *, active: bool, now: datetime,
                     max_visible_slots: int, rotation_seconds: float) -> dict:
    ordered = sorted(
        alarms,
        key=lambda item: (
            item['priority_order'], item['started_at'],
            item['alarm_identity'], item['occurrence_id'],
        ),
    )
    records = {item['occurrence_id']: item for item in ordered}
    if len(records) != len(ordered):
        raise AlarmModelerProjectionError('Duplicate occurrence in tool projection')
    pool = [item['occurrence_id'] for item in ordered if item['attention_required']]
    visible = pool
    if len(pool) > max_visible_slots:
        phase = math.floor(now.timestamp() / rotation_seconds)
        start = (phase * max_visible_slots) % len(pool)
        visible = [pool[(start + idx) % len(pool)] for idx in range(max_visible_slots)]
    visible = visible[:max_visible_slots]
    return {
        'tool_key': tool_key,
        'retired': not active,
        'alarms': records,
        'operator_pool': pool,
        'operator_view': [
            {'slot': index, 'occurrence_id': occurrence_id}
            for index, occurrence_id in enumerate(visible, start=1)
        ],
        'meta': {
            'live_count': len(records),
            'attention_count': len(pool),
            'operator_count': len(visible),
            'max_visible_slots': max_visible_slots,
        },
    }


# Construye una sola proyección atómica para todas las herramientas y retiradas.
def project(
    *,
    current: Mapping[str, object],
    modeler_configuration: Mapping[str, object],
    publication_tool_keys: tuple[str, ...],
    now: datetime,
    max_visible_slots: int = 6,
    rotation_seconds: float = 30.0,
    previous: Mapping[str, object] | None = None,
) -> dict:
    current = validate_document(dict(current), source=True)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise AlarmModelerProjectionError('Modeler clock must be timezone-aware')
    if now.utcoffset().total_seconds() != 0:
        raise AlarmModelerProjectionError('Modeler clock must be UTC')
    if isinstance(max_visible_slots, bool) or not isinstance(max_visible_slots, int) or max_visible_slots < 1:
        raise AlarmModelerProjectionError('max_visible_slots must be a positive integer')
    if isinstance(rotation_seconds, bool) or not isinstance(rotation_seconds, int | float) or not math.isfinite(rotation_seconds) or rotation_seconds <= 0:
        raise AlarmModelerProjectionError('rotation_seconds must be a positive finite number')
    if not isinstance(modeler_configuration, Mapping) or not isinstance(modeler_configuration.get('alarms'), list):
        raise AlarmModelerProjectionError('Modeler materialization is invalid')
    if modeler_configuration.get('resolution_key') != current['state']['resolution_key']:
        raise AlarmModelerProjectionError('Modeler configuration and CURRENT revisions differ')
    if not isinstance(publication_tool_keys, tuple):
        raise AlarmModelerProjectionError('Delivery publication tools are invalid')
    keys = {_required_text(key, 'publication tool') for key in publication_tool_keys}
    if len(keys) != len(publication_tool_keys):
        raise AlarmModelerProjectionError('Duplicate publication tool')
    if previous is not None:
        previous = validate_document(dict(previous))
    configuration: dict[str, dict] = {}
    for entry in modeler_configuration['alarms']:
        if not isinstance(entry, dict) or not isinstance(entry.get('identity'), dict):
            raise AlarmModelerProjectionError('Invalid materialized alarm')
        identity = entry['identity']
        key = f"{_required_text(identity.get('family_key'), 'family_key')}/{_required_text(identity.get('alarm_key'), 'alarm_key')}"
        if key in configuration:
            raise AlarmModelerProjectionError('Duplicate materialized alarm')
        configuration[key] = entry
    if previous is not None:
        keys.update(previous['tools'])
    rows: dict[str, list[dict]] = {tool: [] for tool in keys}
    seen = set()
    for alarm in current['state']['alarms']:
        if not isinstance(alarm, dict):
            raise AlarmModelerProjectionError('Resolved CURRENT alarm is invalid')
        identity = _required_text(alarm.get('identity'), 'alarm identity')
        if identity in seen:
            raise AlarmModelerProjectionError('Duplicate resolved CURRENT alarm')
        seen.add(identity)
        model = configuration.get(identity)
        if model is None:
            raise AlarmModelerProjectionError('Resolved alarm is missing from materialization')
        if not model.get('is_active') or model.get('visibility_mode') != 'VISIBLE':
            continue
        evaluation = alarm.get('evaluation')
        priority = alarm.get('priority')
        if not isinstance(evaluation, dict) or not isinstance(priority, dict):
            raise AlarmModelerProjectionError('Resolved alarm evaluation or priority is invalid')
        if evaluation.get('status') not in ('ACTIVE', 'ERROR'):
            raise AlarmModelerProjectionError('Open alarm evaluation status is invalid')
        if priority.get('disposition') not in (
            'PREDOMINANT', 'ECLIPSED', 'CASCADE_SUPPRESSED', 'DEACTIVATED'
        ):
            raise AlarmModelerProjectionError('Resolved alarm priority is invalid')
        if priority['disposition'] in ('ECLIPSED', 'CASCADE_SUPPRESSED'):
            continue
        managed = alarm.get('directly_managed')
        if not isinstance(managed, bool):
            raise AlarmModelerProjectionError('Resolved alarm management is invalid')
        if not isinstance(alarm.get('assignments'), list):
            raise AlarmModelerProjectionError('Resolved alarm assignments are invalid')
        if any(not isinstance(item, dict) for item in alarm['assignments']):
            raise AlarmModelerProjectionError('Resolved alarm assignment is invalid')
        assigned = {
            _required_text(item.get('tool_key'), 'assigned tool')
            for item in alarm['assignments']
        }
        targets = model.get('visual_targets')
        if not isinstance(targets, list):
            raise AlarmModelerProjectionError('Modeler visual targets are invalid')
        for target in targets:
            if not isinstance(target, dict):
                raise AlarmModelerProjectionError('Modeler target is invalid')
            tool = _required_text(target.get('tool_key'), 'visual target tool')
            if tool not in assigned or tool not in publication_tool_keys:
                continue
            occurrence_id = _required_text(alarm.get('occurrence_id'), 'occurrence_id')
            attention = priority['disposition'] == 'PREDOMINANT' and not managed and alarm.get('deactivation_effect') is None
            rows[tool].append({
                'alarm_identity': identity,
                'family_key': model['identity']['family_key'],
                'alarm_key': model['identity']['alarm_key'],
                'occurrence_id': occurrence_id,
                'episode_id': alarm['episode_id'],
                'started_at': alarm['started_at'],
                'evaluation': evaluation,
                'priority': priority,
                'management_cycle': alarm['management_cycle'],
                'directly_managed': managed,
                'management_effect': alarm['management_effect'],
                'deactivation_effect': alarm['deactivation_effect'],
                'technical_hold': alarm['technical_hold'],
                'attention_required': attention,
                'display_name': model['display_name'],
                'title': model['title'],
                'cause_template': model['cause_template'],
                'kind': model['kind'],
                'criticality': model['criticality'],
                'business_category': model['business_category'],
                'operational_areas': model['operational_areas'],
                'color': model['color'],
                'priority_order': model['priority_order'],
                'messages': model['messages'],
                'default_deactivation_policy': model['default_deactivation_policy'],
                'visual_target': target,
            })
    tools = {
        tool: _tool_projection(
            tool, rows[tool], active=tool in publication_tool_keys, now=now,
            max_visible_slots=max_visible_slots, rotation_seconds=rotation_seconds,
        )
        for tool in sorted(keys)
    }
    document = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'artifact_ref': current['artifact_ref'],
        'source_journal_position': current['journal_position'],
        'source_as_of': current['state']['as_of'],
        'tools': tools,
    }
    document['sha256'] = digest(document)
    return document


# Ignora cambios de reloj/procedencia que no alteran la vista ni la configuración.
def has_semantic_change(previous: Mapping[str, object] | None, next_document: Mapping[str, object]) -> bool:
    if previous is None:
        return True
    return previous['artifact_ref'] != next_document['artifact_ref'] or previous['tools'] != next_document['tools']
