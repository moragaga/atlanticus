from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime
from string import Formatter

DOCUMENT_TYPE = 'ada_alarm_modeler_live_projection'
SCHEMA_VERSION = 3
SOURCE_DOCUMENT_TYPE = 'ada_alarm_engine_resolved_current_state'
SOURCE_SCHEMA_VERSION = 2


# Identifica errores del contrato de proyección sin mezclar persistencia o lógica web.
class AlarmModelerProjectionError(ValueError):
    pass


# Genera un hash estable del documento para proteger integridad e idempotencia.
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


# Runtime v2 transporta valores internos y Modeler v3 publica únicamente la causa resuelta.
def validate_document(document: object, *, source: bool = False) -> dict:
    expected_type = SOURCE_DOCUMENT_TYPE if source else DOCUMENT_TYPE
    # La validación estricta evita interpretar documentos de una versión anterior.
    expected_version = SOURCE_SCHEMA_VERSION if source else SCHEMA_VERSION
    fields = (
        {'document_type', 'schema_version', 'artifact_ref', 'journal_position', 'state', 'sha256'}
        if source
        else {
            'document_type',
            'schema_version',
            'artifact_ref',
            'source_journal_position',
            'source_as_of',
            'tools',
            'sha256',
        }
    )
    if not isinstance(document, dict) or set(document) != fields:
        raise AlarmModelerProjectionError('Projection document has invalid fields')
    if document['document_type'] != expected_type or document['schema_version'] != expected_version:
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
            if (
                set(value)
                != {'tool_key', 'retired', 'alarms', 'operator_pool', 'operator_view', 'meta'}
                or value['tool_key'] != tool_key
                or not isinstance(value['retired'], bool)
            ):
                raise AlarmModelerProjectionError('Modeler tool projection is invalid')
            if not isinstance(value['alarms'], dict) or not isinstance(
                value['operator_pool'], list
            ):
                raise AlarmModelerProjectionError('Modeler tool content is invalid')
            if not isinstance(value['operator_view'], list) or not isinstance(value['meta'], dict):
                raise AlarmModelerProjectionError('Modeler tool view is invalid')
            if value['retired'] and (
                value['alarms'] or value['operator_pool'] or value['operator_view']
            ):
                raise AlarmModelerProjectionError('Retired tool projection must be empty')
            _validate_operator_view(value)
    return document


# Verifica que los slots individuales y el agrupador distributed respeten el contrato publicado.
def _validate_operator_view(tool: dict) -> None:
    # El pool representa todas las alarmas pendientes, incluso las agrupadas.
    pool = tool['operator_pool']
    meta = tool['meta']
    if any(not isinstance(item, str) or item not in tool['alarms'] for item in pool):
        raise AlarmModelerProjectionError('Modeler operator pool is invalid')
    if len(pool) != len(set(pool)):
        raise AlarmModelerProjectionError('Modeler operator pool contains duplicates')
    slots = meta.get('max_visible_slots')
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
        raise AlarmModelerProjectionError('Modeler visible slot limit is invalid')
    if not isinstance(meta.get('rotation_pending'), bool):
        raise AlarmModelerProjectionError('Modeler rotation metadata is invalid')
    if len(tool['operator_view']) > slots:
        raise AlarmModelerProjectionError('Modeler operator view exceeds slot limit')
    occupied = set()
    displayed = set()
    groups = 0
    for item in tool['operator_view']:
        if not isinstance(item, dict):
            raise AlarmModelerProjectionError('Modeler operator slot is invalid')
        position = item.get('slot')
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not 1 <= position <= slots
        ):
            raise AlarmModelerProjectionError('Modeler operator slot is invalid')
        if position in occupied:
            raise AlarmModelerProjectionError('Modeler operator slots must be unique')
        occupied.add(position)
        if set(item) == {'slot', 'occurrence_id'}:
            members = [item['occurrence_id']]
        elif set(item) == {'slot', 'group'}:
            group = item['group']
            if (
                position != slots
                or not isinstance(group, dict)
                or set(group) != {'kind', 'occurrence_ids'}
                or group['kind'] != 'DISTRIBUTED'
                or not isinstance(group['occurrence_ids'], list)
                or len(group['occurrence_ids']) < 2
            ):
                raise AlarmModelerProjectionError('Modeler distributed group is invalid')
            groups += 1
            members = group['occurrence_ids']
            if any(
                tool['alarms']
                .get(member, {})
                .get('visual_target', {})
                .get('process_projection_mode')
                != 'DISTRIBUTED'
                for member in members
                if isinstance(member, str)
            ):
                raise AlarmModelerProjectionError(
                    'Modeler distributed group contains non-distributed alarms'
                )
        else:
            raise AlarmModelerProjectionError('Modeler operator slot has invalid fields')
        for member in members:
            if not isinstance(member, str) or member not in pool or member in displayed:
                raise AlarmModelerProjectionError('Modeler operator slot membership is invalid')
            displayed.add(member)
    distributed_members = {
        occurrence_id
        for occurrence_id in pool
        if isinstance(tool['alarms'][occurrence_id], dict)
        and isinstance(tool['alarms'][occurrence_id].get('visual_target'), dict)
        and tool['alarms'][occurrence_id]['visual_target'].get('process_projection_mode')
        == 'DISTRIBUTED'
    }
    if (len(distributed_members) >= 2) != (groups == 1):
        raise AlarmModelerProjectionError('Modeler distributed group is missing or unexpected')
    if groups and not distributed_members.issubset(displayed):
        raise AlarmModelerProjectionError('Modeler distributed group is incomplete')
    if groups > 1 or meta.get('operator_count') != len(tool['operator_view']):
        raise AlarmModelerProjectionError('Modeler operator view metadata is invalid')


# Exige claves canónicas no vacías para evitar identidades inconsistentes.
def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AlarmModelerProjectionError(f'{label} must be non-empty normalized text')
    return value


# Resuelve únicamente placeholders con nombres simples y valores escalares.
# Si falta algún valor, el template completo queda literal para diagnóstico visual.
def _render_cause(template: str, values: object) -> str:
    if not isinstance(values, Mapping):
        return template
    try:
        for _, field, format_spec, conversion in Formatter().parse(template):
            if field is None:
                continue
            if (
                not field.isidentifier()
                or conversion is not None
                or '{' in format_spec
                or '}' in format_spec
                or field not in values
            ):
                return template
            value = values[field]
            if type(value) not in (str, int, float, bool):
                return template
            if type(value) is float and not math.isfinite(value):
                return template
        return template.format_map(values)
    except (KeyError, ValueError, TypeError, IndexError, AttributeError, OverflowError):
        return template


# Ordena una vez y construye los slots del operador sin alterar el lifecycle de alarmas.
def _tool_projection(
    tool_key: str,
    alarms: list[dict],
    *,
    active: bool,
    now: datetime,
    max_visible_slots: int,
    rotation_seconds: float,
) -> dict:
    ordered = sorted(
        alarms,
        key=lambda item: (
            item['priority_order'],
            item['started_at'],
            item['alarm_identity'],
            item['occurrence_id'],
        ),
    )
    records = {item['occurrence_id']: item for item in ordered}
    if len(records) != len(ordered):
        raise AlarmModelerProjectionError('Duplicate occurrence in tool projection')
    pool = [item['occurrence_id'] for item in ordered if item['attention_required']]
    distributed = []
    for occurrence_id in pool:
        mode = records[occurrence_id]['visual_target'].get('process_projection_mode')
        if mode not in (None, 'GENERIC', 'DISTRIBUTED'):
            raise AlarmModelerProjectionError('Process projection mode is invalid')
        if mode == 'DISTRIBUTED':
            distributed.append(occurrence_id)
    # Dos o más alarms DISTRIBUTED comparten el último slot; una sola entra al flujo normal.
    grouped = len(distributed) >= 2
    if grouped and max_visible_slots != 6:
        raise AlarmModelerProjectionError('Distributed projection requires six visible slots')
    distributed_members = set(distributed)
    normal_pool = [item for item in pool if item not in distributed_members] if grouped else pool
    # Reservar el último slot reduce en uno la capacidad del carousel normal.
    normal_slots = max_visible_slots - int(grouped)
    # El agrupador por sí solo no obliga a rotar el carousel normal.
    rotation_pending = normal_slots > 0 and len(normal_pool) > normal_slots
    visible = normal_pool
    if rotation_pending:
        phase = math.floor(now.timestamp() / rotation_seconds)
        start = (phase * normal_slots) % len(normal_pool)
        visible = [normal_pool[(start + idx) % len(normal_pool)] for idx in range(normal_slots)]
    visible = visible[:normal_slots]
    view = [
        {'slot': index, 'occurrence_id': occurrence_id}
        for index, occurrence_id in enumerate(visible, start=1)
    ]
    # El agrupador conserva los miembros ordenados, pero no selecciona ni rota una alarma interna.
    if grouped:
        view.append(
            {
                'slot': max_visible_slots,
                'group': {'kind': 'DISTRIBUTED', 'occurrence_ids': distributed},
            }
        )
    return {
        'tool_key': tool_key,
        'retired': not active,
        'alarms': records,
        'operator_pool': pool,
        'operator_view': view,
        'meta': {
            'live_count': len(records),
            'attention_count': len(pool),
            'operator_count': len(view),
            'max_visible_slots': max_visible_slots,
            'rotation_pending': rotation_pending,
        },
    }


# Cruza CURRENT con la materialización efectiva y publica una proyección por herramienta.
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
    if (
        isinstance(max_visible_slots, bool)
        or not isinstance(max_visible_slots, int)
        or max_visible_slots < 1
    ):
        raise AlarmModelerProjectionError('max_visible_slots must be a positive integer')
    if (
        isinstance(rotation_seconds, bool)
        or not isinstance(rotation_seconds, int | float)
        or not math.isfinite(rotation_seconds)
        or rotation_seconds <= 0
    ):
        raise AlarmModelerProjectionError('rotation_seconds must be a positive finite number')
    if not isinstance(modeler_configuration, Mapping) or not isinstance(
        modeler_configuration.get('alarms'), list
    ):
        raise AlarmModelerProjectionError('Modeler materialization is invalid')
    if modeler_configuration.get('resolution_key') != current['state']['resolution_key']:
        raise AlarmModelerProjectionError('Modeler configuration and CURRENT revisions differ')
    if not isinstance(publication_tool_keys, tuple):
        raise AlarmModelerProjectionError('Delivery publication tools are invalid')
    keys = {_required_text(key, 'publication tool') for key in publication_tool_keys}
    if len(keys) != len(publication_tool_keys):
        raise AlarmModelerProjectionError('Duplicate publication tool')
    # La continuidad solo acepta snapshots publicados bajo el contrato actual.
    if previous is not None:
        previous = validate_document(dict(previous))
    configuration: dict[str, dict] = {}
    for entry in modeler_configuration['alarms']:
        if not isinstance(entry, dict) or not isinstance(entry.get('identity'), dict):
            raise AlarmModelerProjectionError('Invalid materialized alarm')
        identity = entry['identity']
        key = f'{_required_text(identity.get("family_key"), "family_key")}/{_required_text(identity.get("alarm_key"), "alarm_key")}'
        if key in configuration:
            raise AlarmModelerProjectionError('Duplicate materialized alarm')
        configuration[key] = entry
    # La continuidad solo acepta snapshots publicados bajo el contrato actual.
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
        public_evaluation = {key: value for key, value in evaluation.items() if key != 'cause_values'}
        if priority.get('disposition') not in (
            'PREDOMINANT',
            'ECLIPSED',
            'CASCADE_SUPPRESSED',
            'DEACTIVATED',
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
            _required_text(item.get('tool_key'), 'assigned tool') for item in alarm['assignments']
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
            attention = (
                priority['disposition'] == 'PREDOMINANT'
                and not managed
                and alarm.get('deactivation_effect') is None
            )
            rows[tool].append(
                {
                    'alarm_identity': identity,
                    'family_key': model['identity']['family_key'],
                    'alarm_key': model['identity']['alarm_key'],
                    'occurrence_id': occurrence_id,
                    'episode_id': alarm['episode_id'],
                    'started_at': alarm['started_at'],
                    'evaluation': public_evaluation,
                    'priority': priority,
                    'management_cycle': alarm['management_cycle'],
                    'directly_managed': managed,
                    'management_effect': alarm['management_effect'],
                    'deactivation_effect': alarm['deactivation_effect'],
                    'technical_hold': alarm['technical_hold'],
                    'attention_required': attention,
                    'display_name': model['display_name'],
                    'title': model['title'],
                    'cause_text': _render_cause(
                        model['cause_template'], evaluation.get('cause_values')
                    ),
                    'kind': model['kind'],
                    'criticality': model['criticality'],
                    'business_category': model['business_category'],
                    'operational_areas': model['operational_areas'],
                    'color': model['color'],
                    'priority_order': model['priority_order'],
                    'messages': model['messages'],
                    'default_deactivation_policy': model['default_deactivation_policy'],
                    'visual_target': target,
                }
            )
    tools = {
        tool: _tool_projection(
            tool,
            rows[tool],
            active=tool in publication_tool_keys,
            now=now,
            max_visible_slots=max_visible_slots,
            rotation_seconds=rotation_seconds,
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


# Solo requiere publicar si cambian la referencia efectiva o los datos visibles.
def has_semantic_change(
    previous: Mapping[str, object] | None, next_document: Mapping[str, object]
) -> bool:
    if previous is None:
        return True
    return (
        previous['artifact_ref'] != next_document['artifact_ref']
        or previous['tools'] != next_document['tools']
    )
