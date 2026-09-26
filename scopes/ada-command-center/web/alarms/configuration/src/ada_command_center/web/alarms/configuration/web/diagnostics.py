from __future__ import annotations

from collections.abc import Mapping

from ada_command_center.web.alarms.configuration.web.labels import field_label
from ada_command_center.web.alarms.configuration.web.parameters import parameter_issues

_RULE_FIELDS = (
    ('identity.alarm_key', 'general', 'Alarm key'),
    ('rule_name', 'general', 'Rule name'),
    ('display_name', 'general', 'Display name'),
    ('title', 'general', 'Title'),
    ('cause_template', 'general', 'Cause template'),
    ('is_active', 'classification', 'Active'),
    ('visibility_mode', 'classification', 'Visibility'),
    ('is_special_condition', 'classification', 'Special condition'),
    ('kind', 'classification', 'Kind'),
    ('criticality', 'classification', 'Criticality'),
    ('business_category', 'classification', 'Business category'),
    ('operational_areas', 'classification', 'Operational areas'),
    ('color', 'classification', 'Color'),
    ('evaluator_key', 'evaluation', 'Evaluator key'),
    ('priority_group', 'evaluation', 'Priority group'),
    ('priority_order', 'evaluation', 'Priority order'),
    ('default_deactivation.enabled', 'deactivation', 'Enabled'),
    ('escalation.origin_tool_key', 'escalation', 'Origin tool key'),
)

_SECTION_LABELS = {
    'general': 'Información general',
    'classification': 'Clasificación',
    'evaluation': 'Evaluación y prioridad',
    'deactivation': 'Desactivación',
    'escalation': 'Origen y escalamiento',
}


def authoring_issues(document: Mapping[str, object] | None) -> tuple[str, ...]:
    if document is None:
        return ()
    result: list[str] = []
    rules = document.get('rules')
    messages = document.get('messages')
    for index, entry in enumerate(rules if isinstance(rules, list) else []):
        if not isinstance(entry, dict):
            result.append(f'Regla {index + 1}: estructura no reconocida.')
            continue
        identity = entry.get('identity')
        family = identity.get('family_key') if isinstance(identity, dict) else None
        if not isinstance(family, str) or not family.strip():
            result.append(f'Regla {index + 1} · Información general: selecciona una familia.')
        for path, section, label in _RULE_FIELDS:
            value = _field(entry, path)
            if _missing(value):
                result.append(
                    f'Regla {index + 1} · {_SECTION_LABELS[section]}: '
                    f'completa «{field_label(label)}».'
                )
        deactivation = entry.get('default_deactivation')
        if isinstance(deactivation, dict) and deactivation.get('enabled') is True:
            if _missing(deactivation.get('max_duration_hours')):
                result.append(f'Regla {index + 1} · Desactivación: indica la duración máxima.')
            if deactivation.get('approval_required') is None:
                result.append(
                    f'Regla {index + 1} · Desactivación: especifica si requiere aprobación.'
                )
        priority_order = entry.get('priority_order')
        if priority_order is not None and (type(priority_order) is not int or priority_order <= 0):
            result.append(
                f'Regla {index + 1} · Evaluación y prioridad: el orden debe ser positivo.'
            )
        for parameter_issue in parameter_issues(entry):
            result.append(f'Regla {index + 1} · Evaluación y prioridad: {parameter_issue}')
        parameters = entry.get('parameters')
        if not isinstance(parameters, dict):
            result.append(
                f'Regla {index + 1} · Evaluación y prioridad: '
                'los parámetros deben ser un objeto JSON válido.'
            )
    for index, entry in enumerate(messages if isinstance(messages, list) else []):
        if not isinstance(entry, dict):
            result.append(f'Mensaje {index + 1}: estructura no reconocida.')
            continue
        for field, label in (
            ('message_key', 'Identificador'),
            ('scope', 'Alcance'),
            ('display_text', 'Texto'),
            ('is_active', 'Estado'),
        ):
            if _missing(entry.get(field)):
                result.append(f'Mensaje {index + 1}: completa «{label}».')
        if entry.get('scope') == 'FAMILY' and _missing(entry.get('family_key')):
            result.append(f'Mensaje {index + 1}: selecciona una familia.')
    return tuple(result)


def _field(document: dict[str, object], path: str) -> object:
    result: object = document
    for part in path.split('.'):
        if not isinstance(result, dict):
            return None
        result = result.get(part)
    return result


def _missing(value: object) -> bool:
    return value is None or isinstance(value, str) and not value.strip() or value == []


def readiness_hints(document: Mapping[str, object] | None) -> tuple[str, ...]:
    if document is None:
        return ()
    rules = document.get('rules')
    hints: list[str] = []
    for index, rule in enumerate(rules if isinstance(rules, list) else []):
        if not isinstance(rule, dict):
            continue
        escalation = rule.get('escalation')
        steps = escalation.get('steps') if isinstance(escalation, dict) else None
        enabled = (
            [step for step in steps if isinstance(step, dict) and step.get('is_enabled') is True]
            if isinstance(steps, list)
            else []
        )
        if rule.get('criticality') == 'C3' and enabled:
            hints.append(
                f'Regla {index + 1} · Escalamiento: C3 no admite pasos habilitados '
                'en Materialization. Desactívalos o elimínalos.'
            )
        if rule.get('criticality') == 'C1' and any(
            step.get('wait_minutes_from_previous_step') not in (None, 0) for step in enabled
        ):
            hints.append(f'Regla {index + 1} · Escalamiento: C1 sólo admite pasos inmediatos.')
        if rule.get('criticality') == 'C2' and any(
            type(step.get('wait_minutes_from_previous_step')) is not int
            or step['wait_minutes_from_previous_step'] <= 0
            for step in enabled
        ):
            hints.append(
                f'Regla {index + 1} · Escalamiento: C2 exige una espera positiva '
                'por destino habilitado.'
            )
    return tuple(hints)
