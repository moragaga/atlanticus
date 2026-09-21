from __future__ import annotations

# Transformaciones puras del documento transitorio usado por el editor estructurado.
# Cada operación devuelve una copia para evitar mutar accidentalmente el estado que Dash conserva.
# Estas funciones no deciden validez de dominio: Save/Publish siguen delegando en AlarmConfiguration.


import json
from copy import deepcopy

from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolReferenceCatalog,
)


def empty_authoring_document() -> dict[str, object]:
    return {'rules': [], 'messages': []}


def normalize_authoring_document(document: dict[str, object] | None) -> dict[str, object]:
    if document is None:
        return empty_authoring_document()
    value = deepcopy(document)
    if not isinstance(value.get('rules'), list):
        value['rules'] = []
    if not isinstance(value.get('messages'), list):
        value['messages'] = []
    return value


def tool_reference_catalog_to_document(
    catalog: AlarmToolReferenceCatalog | None,
) -> dict[str, object] | None:
    if catalog is None:
        return None
    return {
        'catalog_revision': catalog.catalog_revision,
        'tools': [
            {
                'tool_key': tool.tool_key,
                'display_name': tool.display_name,
                'kind': tool.kind.value,
                'source_release_id': tool.source_release_id.value,
                'components': [
                    {
                        'component_key': component.component_key,
                        'display_name': component.display_name,
                        'subcomponents': [
                            {
                                'owner_component_key': subcomponent.owner_component_key,
                                'subcomponent_key': subcomponent.subcomponent_key,
                                'display_name': subcomponent.display_name,
                            }
                            for subcomponent in component.subcomponents
                        ],
                    }
                    for component in tool.components
                ],
            }
            for tool in catalog.tools
        ],
    }


def tool_suggestions(reference_document: dict[str, object] | None) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            'value': tool['tool_key'],
            'label': f'{tool["display_name"]} ({tool["tool_key"]})',
        }
        for tool in _tools(reference_document)
    )


def component_suggestions(
    reference_document: dict[str, object] | None,
    tool_key: str | None,
) -> tuple[dict[str, str], ...]:
    tool = _tool(reference_document, tool_key)
    if tool is None:
        return ()
    return tuple(
        {
            'value': component['component_key'],
            'label': f'{component["display_name"]} ({component["component_key"]})',
        }
        for component in _components(tool)
    )


def subcomponent_suggestions(
    reference_document: dict[str, object] | None,
    tool_key: str | None,
    component_keys: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, str], ...]:
    tool = _tool(reference_document, tool_key)
    if tool is None:
        return ()
    requested = set(component_keys or ())
    components = _components(tool)
    selected = [item for item in components if item['component_key'] in requested]
    visible_from = selected or components
    seen: set[tuple[str, str]] = set()
    values: list[dict[str, str]] = []
    for component in visible_from:
        for subcomponent in _subcomponents(component):
            identity = (
                subcomponent['owner_component_key'],
                subcomponent['subcomponent_key'],
            )
            if identity in seen:
                continue
            seen.add(identity)
            values.append(
                {
                    'owner_component_key': identity[0],
                    'subcomponent_key': identity[1],
                    'display_name': subcomponent['display_name'],
                }
            )
    return tuple(values)


def add_rule(document: dict[str, object]) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _rules(value).append(_new_rule())
    return value


def remove_rule(document: dict[str, object], rule_index: int) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _rules(value)[rule_index]
    return value


def add_message(document: dict[str, object]) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _messages(value).append(_new_message())
    return value


def remove_message(document: dict[str, object], message_index: int) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _messages(value)[message_index]
    return value


def set_rule_field(
    document: dict[str, object],
    rule_index: int,
    field: str,
    field_value: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    rule = _rule(value, rule_index)
    if field in {
        'rule_name',
        'display_name',
        'title',
        'cause_template',
        'is_active',
        'visibility_mode',
        'is_special_condition',
        'kind',
        'criticality',
        'business_category',
        'operational_areas',
        'color',
        'evaluator_key',
        'priority_group',
        'priority_order',
        'message_keys',
    }:
        rule[field] = deepcopy(field_value)
        return value
    if field == 'parameters':
        rule[field] = _parameters_value(field_value)
        return value
    if field in {'identity.family_key', 'identity.alarm_key'}:
        identity = _mapping(rule, 'identity')
        identity[field.removeprefix('identity.')] = field_value
        return value
    if field == 'reappearance.after_minutes':
        _mapping(rule, 'reappearance')['after_minutes'] = field_value
        return value
    if field == 'reappearance.special_conditions':
        _mapping(rule, 'reappearance')['special_conditions'] = [
            _identity_document(item) for item in _string_list(field_value)
        ]
        return value
    if field.startswith('default_deactivation.'):
        name = field.removeprefix('default_deactivation.')
        deactivation = _mapping(rule, 'default_deactivation')
        deactivation[name] = field_value
        if name == 'enabled' and field_value is False:
            deactivation['max_duration_hours'] = None
            deactivation['approval_required'] = False
        return value
    if field == 'escalation.origin_tool_key':
        _mapping(rule, 'escalation')['origin_tool_key'] = field_value
        return value
    raise ValueError(f'Unsupported Alarm Configuration rule field: {field}')


def add_escalation_step(document: dict[str, object], rule_index: int) -> dict[str, object]:
    value = normalize_authoring_document(document)
    steps = _steps(_rule(value, rule_index))
    numeric_orders = [
        step.get('step_order')
        for step in steps
        if isinstance(step.get('step_order'), int) and not isinstance(step.get('step_order'), bool)
    ]
    steps.append(
        {
            'step_order': max(numeric_orders, default=0) + 1,
            'target_tool_key': '',
            'is_enabled': None,
            'wait_minutes_from_previous_step': None,
        }
    )
    return value


def remove_escalation_step(
    document: dict[str, object],
    rule_index: int,
    step_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _steps(_rule(value, rule_index))[step_index]
    return value


def set_escalation_step_field(
    document: dict[str, object],
    rule_index: int,
    step_index: int,
    field: str,
    field_value: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    step = _steps(_rule(value, rule_index))[step_index]
    if field not in {
        'step_order',
        'target_tool_key',
        'is_enabled',
        'wait_minutes_from_previous_step',
    }:
        raise ValueError(f'Unsupported Alarm Configuration escalation field: {field}')
    step[field] = field_value
    return value


def add_visual_target(document: dict[str, object], rule_index: int) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _visual_targets(_rule(value, rule_index)).append(
        {
            'tool_key': '',
            'component_keys': [],
            'subcomponents': [],
            'process_projection_mode': None,
        }
    )
    return value


def remove_visual_target(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _visual_targets(_rule(value, rule_index))[target_index]
    return value


def set_visual_target_field(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
    field: str,
    field_value: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    target = _visual_targets(_rule(value, rule_index))[target_index]
    if field not in {'tool_key', 'process_projection_mode'}:
        raise ValueError(f'Unsupported Alarm Configuration visual target field: {field}')
    if field == 'tool_key' and target.get('tool_key') != field_value:
        target['component_keys'] = []
        target['subcomponents'] = []
    target[field] = field_value
    return value


def add_component_key(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _component_keys(_visual_target(_rule(value, rule_index), target_index)).append('')
    return value


def remove_component_key(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
    component_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _component_keys(_visual_target(_rule(value, rule_index), target_index))[component_index]
    return value


def set_component_key(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
    component_index: int,
    component_key: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _component_keys(_visual_target(_rule(value, rule_index), target_index))[component_index] = (
        component_key
    )
    return value


def add_subcomponent(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    _subcomponent_targets(_visual_target(_rule(value, rule_index), target_index)).append(
        {'owner_component_key': '', 'subcomponent_key': ''}
    )
    return value


def remove_subcomponent(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
    subcomponent_index: int,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    del _subcomponent_targets(_visual_target(_rule(value, rule_index), target_index))[
        subcomponent_index
    ]
    return value


def set_subcomponent_field(
    document: dict[str, object],
    rule_index: int,
    target_index: int,
    subcomponent_index: int,
    field: str,
    field_value: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    subcomponent = _subcomponent_targets(_visual_target(_rule(value, rule_index), target_index))[
        subcomponent_index
    ]
    if field not in {'owner_component_key', 'subcomponent_key'}:
        raise ValueError(f'Unsupported Alarm Configuration subcomponent field: {field}')
    subcomponent[field] = field_value
    return value


def set_message_field(
    document: dict[str, object],
    message_index: int,
    field: str,
    field_value: object,
) -> dict[str, object]:
    value = normalize_authoring_document(document)
    message = _message(value, message_index)
    if field in {'message_key', 'display_text', 'is_active'}:
        message[field] = field_value
        return value
    if field == 'scope':
        message['scope'] = field_value
        if field_value == 'GLOBAL':
            message['family_key'] = None
        elif message.get('family_key') is None:
            message['family_key'] = ''
        return value
    if field == 'family_key':
        message['family_key'] = field_value
        return value
    if field == 'deactivation_override.present':
        if field_value:
            if message.get('deactivation_override') is None:
                message['deactivation_override'] = {
                    'enabled': None,
                    'max_duration_hours': None,
                    'approval_required': None,
                }
        else:
            message['deactivation_override'] = None
        return value
    if field.startswith('deactivation_override.'):
        override = message.get('deactivation_override')
        if not isinstance(override, dict):
            override = {
                'enabled': None,
                'max_duration_hours': None,
                'approval_required': None,
            }
            message['deactivation_override'] = override
        name = field.removeprefix('deactivation_override.')
        override[name] = field_value
        if name == 'enabled' and field_value is False:
            override['max_duration_hours'] = None
            override['approval_required'] = False
        return value
    raise ValueError(f'Unsupported Alarm Configuration message field: {field}')


def _new_rule() -> dict[str, object]:
    return {
        'identity': {'family_key': '', 'alarm_key': ''},
        'rule_name': '',
        'display_name': '',
        'title': '',
        'cause_template': '',
        'is_active': None,
        'visibility_mode': None,
        'is_special_condition': None,
        'kind': None,
        'criticality': None,
        'business_category': None,
        'operational_areas': [],
        'color': None,
        'evaluator_key': '',
        'parameters': {},
        'priority_group': '',
        'priority_order': None,
        'message_keys': [],
        'reappearance': {'after_minutes': None, 'special_conditions': []},
        'default_deactivation': {
            'enabled': None,
            'max_duration_hours': None,
            'approval_required': None,
        },
        'escalation': {'origin_tool_key': '', 'steps': []},
        'visual_targets': [],
    }


def _new_message() -> dict[str, object]:
    return {
        'message_key': '',
        'scope': None,
        'family_key': None,
        'display_text': '',
        'is_active': None,
        'deactivation_override': None,
    }


def _parameters_value(value: object) -> object:
    if not isinstance(value, str):
        return deepcopy(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _identity_document(value: str) -> dict[str, str]:
    family_key, separator, alarm_key = value.partition('/')
    if not separator:
        return {'family_key': '', 'alarm_key': value}
    return {'family_key': family_key, 'alarm_key': alarm_key}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _rules(document: dict[str, object]) -> list[dict[str, object]]:
    value = document['rules']
    if not isinstance(value, list):
        raise ValueError('Alarm Configuration rules must be a list')
    return value


def _messages(document: dict[str, object]) -> list[dict[str, object]]:
    value = document['messages']
    if not isinstance(value, list):
        raise ValueError('Alarm Configuration messages must be a list')
    return value


def _rule(document: dict[str, object], index: int) -> dict[str, object]:
    value = _rules(document)[index]
    if not isinstance(value, dict):
        raise ValueError('Alarm Configuration rule must be an object')
    return value


def _message(document: dict[str, object], index: int) -> dict[str, object]:
    value = _messages(document)[index]
    if not isinstance(value, dict):
        raise ValueError('Alarm Configuration message must be an object')
    return value


def _mapping(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        value = {}
        document[key] = value
    return value


def _steps(rule: dict[str, object]) -> list[dict[str, object]]:
    escalation = _mapping(rule, 'escalation')
    value = escalation.get('steps')
    if not isinstance(value, list):
        value = []
        escalation['steps'] = value
    return value


def _visual_targets(rule: dict[str, object]) -> list[dict[str, object]]:
    value = rule.get('visual_targets')
    if not isinstance(value, list):
        value = []
        rule['visual_targets'] = value
    return value


def _visual_target(rule: dict[str, object], index: int) -> dict[str, object]:
    value = _visual_targets(rule)[index]
    if not isinstance(value, dict):
        raise ValueError('Alarm Configuration visual target must be an object')
    return value


def _component_keys(target: dict[str, object]) -> list[object]:
    value = target.get('component_keys')
    if not isinstance(value, list):
        value = []
        target['component_keys'] = value
    return value


def _subcomponent_targets(target: dict[str, object]) -> list[dict[str, object]]:
    value = target.get('subcomponents')
    if not isinstance(value, list):
        value = []
        target['subcomponents'] = value
    return value


def _tools(reference_document: dict[str, object] | None) -> list[dict[str, str | object]]:
    if reference_document is None:
        return []
    value = reference_document.get('tools')
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool(
    reference_document: dict[str, object] | None,
    tool_key: str | None,
) -> dict[str, str | object] | None:
    if not isinstance(tool_key, str):
        return None
    for tool in _tools(reference_document):
        if tool.get('tool_key') == tool_key:
            return tool
    return None


def _components(tool: dict[str, str | object]) -> list[dict[str, str | object]]:
    value = tool.get('components')
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _subcomponents(component: dict[str, str | object]) -> list[dict[str, str]]:
    value = component.get('subcomponents')
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
