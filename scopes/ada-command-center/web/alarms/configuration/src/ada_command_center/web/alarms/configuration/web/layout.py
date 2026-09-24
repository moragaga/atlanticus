from __future__ import annotations

import json
from collections.abc import Mapping

from dash import dcc, html

from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ProcessAlarmProjectionMode,
    VisibilityMode,
)
from ada_command_center.web.alarms.configuration.web.authoring import (
    component_suggestions,
    empty_authoring_document,
    subcomponent_suggestions,
    tool_suggestions,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    ADD_MESSAGE_BUTTON_ID,
    ADD_RULE_BUTTON_ID,
    AUTHORING_STORE_ID,
    COMPONENT_ADD_TYPE,
    COMPONENT_FIELD_TYPE,
    COMPONENT_REMOVE_TYPE,
    DOCUMENT_STATUS_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    MESSAGE_FIELD_TYPE,
    MESSAGE_REMOVE_TYPE,
    MESSAGES_EDITOR_ID,
    MOUNT_STORE_ID,
    PROJECTION_NAME_ID,
    RULE_FIELD_TYPE,
    RULE_REMOVE_TYPE,
    RULES_EDITOR_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
    STEP_ADD_TYPE,
    STEP_FIELD_TYPE,
    STEP_REMOVE_TYPE,
    SUBCOMPONENT_ADD_TYPE,
    SUBCOMPONENT_FIELD_TYPE,
    SUBCOMPONENT_REMOVE_TYPE,
    TARGET_ADD_TYPE,
    TARGET_FIELD_TYPE,
    TARGET_REMOVE_TYPE,
    TOOL_DATALIST_ID,
    TOOL_REFERENCE_STATUS_ID,
    TOOL_REFERENCE_STORE_ID,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)


def build_alarm_configuration_admin(context: AlarmConfigurationAdminWebContext) -> object:
    return html.Div(
        [
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            dcc.Store(
                id=AUTHORING_STORE_ID,
                data=empty_authoring_document(),
                storage_type='memory',
            ),
            dcc.Store(id=TOOL_REFERENCE_STORE_ID, data=None, storage_type='memory'),
            _runtime_context(context),
            html.Section(
                [
                    html.H3('Alarm Configuration'),
                    html.P(
                        'Structured authoring edits the same durable Rules + Messages contract. '
                        'Tool references are suggestions and do not determine intrinsic validity.'
                    ),
                    html.Div(id=TOOL_REFERENCE_STATUS_ID),
                    html.Div(id=DOCUMENT_STATUS_ID),
                ],
                className='ada-command-center-alarm-editor__overview',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H4('Rules'),
                            html.Button(
                                'Add rule',
                                id=ADD_RULE_BUTTON_ID,
                                n_clicks=0,
                                type='button',
                            ),
                        ]
                    ),
                    html.Div(id=RULES_EDITOR_ID),
                ],
                className='ada-command-center-alarm-editor__rules',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H4('Messages'),
                            html.Button(
                                'Add message',
                                id=ADD_MESSAGE_BUTTON_ID,
                                n_clicks=0,
                                type='button',
                            ),
                        ]
                    ),
                    html.Div(id=MESSAGES_EDITOR_ID),
                ],
                className='ada-command-center-alarm-editor__messages',
            ),
            html.Section(
                [
                    html.Button(
                        'Save local draft',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                    ),
                    html.Div(id=SAVE_RESULT_ID),
                ],
                className='ada-command-center-alarm-editor__save',
            ),
        ],
        className='ada-command-center-alarm-editor',
    )


def build_structured_editors(
    authoring_document: dict[str, object] | None,
    reference_document: dict[str, object] | None,
) -> tuple[object, object]:
    document = authoring_document or empty_authoring_document()
    rules = document.get('rules')
    messages = document.get('messages')
    raw_rules = rules if isinstance(rules, list) else []
    raw_messages = messages if isinstance(messages, list) else []
    tools = tool_suggestions(reference_document)
    tool_datalist = html.Datalist(
        id=TOOL_DATALIST_ID,
        children=[html.Option(value=item['value'], label=item['label']) for item in tools],
    )
    rule_cards = [
        (
            index,
            rule,
            _rule_editor(index, rule, raw_rules, raw_messages, reference_document),
        )
        for index, rule in enumerate(raw_rules)
        if isinstance(rule, dict)
    ]
    message_cards = [
        (index, message, _message_editor(index, message))
        for index, message in enumerate(raw_messages)
        if isinstance(message, dict)
    ]
    return (
        _collection_editor(rule_cards, kind='rule', datalist=tool_datalist),
        _collection_editor(message_cards, kind='message'),
    )


def _collection_editor(
    cards: list[tuple[int, dict[str, object], object]],
    *,
    kind: str,
    datalist: object | None = None,
) -> object:
    if not cards:
        return html.Div(
            [
                datalist,
                html.P(
                    f'No {kind}s in this draft.',
                    className='ada-command-center-alarm-editor__empty',
                ),
            ],
            className='ada-command-center-alarm-editor__collection',
        )

    navigation = []
    details = []
    for index, record, editor in cards:
        anchor = f'alarm-configuration-{kind}-detail-{index}'
        legend = editor.children[0]
        title = (
            legend.children if isinstance(legend.children, str) else f'{kind.title()} {index + 1}'
        )
        navigation.append(
            html.A(
                [
                    html.Span(
                        f'{index + 1:02d}',
                        className='ada-command-center-alarm-editor__item-number',
                    ),
                    html.Span(
                        [
                            html.Strong(title),
                            html.Small(_record_subtitle(record, kind)),
                        ],
                        className='ada-command-center-alarm-editor__item-copy',
                    ),
                ],
                href=f'#{anchor}',
                className='ada-command-center-alarm-editor__item',
            )
        )
        details.append(
            html.Section(
                editor,
                id=anchor,
                className='ada-command-center-alarm-editor__detail',
            )
        )

    return html.Div(
        [
            datalist,
            html.Div(
                [
                    html.Nav(
                        [html.H5(f'{kind.title()}s ({len(navigation)})'), *navigation],
                        className='ada-command-center-alarm-editor__index',
                        **{'aria-label': f'{kind.title()} navigation'},
                    ),
                    html.Div(details, className='ada-command-center-alarm-editor__details'),
                ],
                className='ada-command-center-alarm-editor__split',
            ),
        ],
        className='ada-command-center-alarm-editor__collection',
    )


def _record_subtitle(record: dict[str, object], kind: str) -> str:
    active = record.get('is_active')
    status = 'Active' if active is True else 'Inactive' if active is False else 'Not set'
    if kind == 'message':
        scope = record.get('scope') or 'Unclassified'
        return f'{scope} · {status}'
    category = record.get('kind') or 'Unclassified'
    criticality = record.get('criticality') or 'No criticality'
    return f'{category} · {criticality} · {status}'


def _runtime_context(context: AlarmConfigurationAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Source'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ]
            ),
            html.Div(
                [
                    html.Span('Projection'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ]
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=html.Button('Import JSON', type='button'),
                        accept='.json,application/json',
                        multiple=False,
                    ),
                    html.Span(
                        'Import replaces the browser draft only after the contract is valid.'
                    ),
                    html.Div(id=IMPORT_RESULT_ID),
                ]
            ),
        ],
        className='ada-command-center-alarm-editor__context',
    )


def _rule_editor(
    rule_index: int,
    rule: dict[str, object],
    rules: list[object],
    messages: list[object],
    reference_document: dict[str, object] | None,
) -> object:
    identity = _mapping(rule.get('identity'))
    reappearance = _mapping(rule.get('reappearance'))
    deactivation = _mapping(rule.get('default_deactivation'))
    escalation = _mapping(rule.get('escalation'))
    steps = _list(escalation.get('steps'))
    targets = _list(rule.get('visual_targets'))
    family_key = _string(identity.get('family_key'))
    priority_group = _string(rule.get('priority_group'))
    title = _string(rule.get('display_name')) or _string(rule.get('rule_name'))
    title = title or f'Rule {rule_index + 1}'
    message_options = _message_options(messages, family_key, _list(rule.get('message_keys')))
    special_options = _special_condition_options(
        rules,
        family_key,
        priority_group,
        _list(reappearance.get('special_conditions')),
    )
    return html.Fieldset(
        [
            html.Legend(title),
            html.Button(
                'Remove rule',
                id={'type': RULE_REMOVE_TYPE, 'rule': rule_index},
                n_clicks=0,
                type='button',
            ),
            _group(
                'Identity and presentation',
                [
                    _text_field(
                        rule_index,
                        'identity.family_key',
                        'Family key',
                        identity.get('family_key'),
                    ),
                    _text_field(
                        rule_index,
                        'identity.alarm_key',
                        'Alarm key',
                        identity.get('alarm_key'),
                    ),
                    _text_field(rule_index, 'rule_name', 'Rule name', rule.get('rule_name')),
                    _text_field(
                        rule_index, 'display_name', 'Display name', rule.get('display_name')
                    ),
                    _text_field(rule_index, 'title', 'Title', rule.get('title')),
                    _text_field(
                        rule_index,
                        'cause_template',
                        'Cause template',
                        rule.get('cause_template'),
                    ),
                ],
            ),
            _group(
                'Classification',
                [
                    _bool_field(rule_index, 'is_active', 'Active', rule.get('is_active')),
                    _enum_field(
                        rule_index,
                        'visibility_mode',
                        'Visibility',
                        rule.get('visibility_mode'),
                        VisibilityMode,
                    ),
                    _bool_field(
                        rule_index,
                        'is_special_condition',
                        'Special condition',
                        rule.get('is_special_condition'),
                    ),
                    _enum_field(rule_index, 'kind', 'Kind', rule.get('kind'), AlarmKind),
                    _enum_field(
                        rule_index,
                        'criticality',
                        'Criticality',
                        rule.get('criticality'),
                        Criticality,
                    ),
                    _enum_field(
                        rule_index,
                        'business_category',
                        'Business category',
                        rule.get('business_category'),
                        BusinessCategory,
                    ),
                    _multi_enum_field(
                        rule_index,
                        'operational_areas',
                        'Operational areas',
                        rule.get('operational_areas'),
                        OperationalArea,
                    ),
                    _enum_field(rule_index, 'color', 'Color', rule.get('color'), AlarmColor),
                ],
            ),
            _group(
                'Evaluation and priority',
                [
                    _text_field(
                        rule_index, 'evaluator_key', 'Evaluator key', rule.get('evaluator_key')
                    ),
                    _text_field(
                        rule_index,
                        'parameters',
                        'Parameters JSON',
                        _parameters_text(rule.get('parameters')),
                    ),
                    _text_field(
                        rule_index, 'priority_group', 'Priority group', rule.get('priority_group')
                    ),
                    _number_field(
                        rule_index, 'priority_order', 'Priority order', rule.get('priority_order')
                    ),
                    _dropdown_field(
                        rule_index,
                        'message_keys',
                        'Messages',
                        _string_list(rule.get('message_keys')),
                        message_options,
                        multi=True,
                    ),
                ],
            ),
            _group(
                'Reappearance',
                [
                    _number_field(
                        rule_index,
                        'reappearance.after_minutes',
                        'After minutes',
                        reappearance.get('after_minutes'),
                    ),
                    _dropdown_field(
                        rule_index,
                        'reappearance.special_conditions',
                        'Special conditions',
                        _identity_values(reappearance.get('special_conditions')),
                        special_options,
                        multi=True,
                    ),
                ],
            ),
            _group(
                'Default deactivation',
                [
                    _bool_field(
                        rule_index,
                        'default_deactivation.enabled',
                        'Enabled',
                        deactivation.get('enabled'),
                    ),
                    _number_field(
                        rule_index,
                        'default_deactivation.max_duration_hours',
                        'Max duration hours',
                        deactivation.get('max_duration_hours'),
                    ),
                    _bool_field(
                        rule_index,
                        'default_deactivation.approval_required',
                        'Approval required',
                        deactivation.get('approval_required'),
                    ),
                ],
            ),
            _escalation_editor(rule_index, escalation, steps),
            _visual_targets_editor(rule_index, targets, reference_document),
        ]
    )


def _escalation_editor(
    rule_index: int,
    escalation: Mapping[str, object],
    steps: list[object],
) -> object:
    children: list[object] = [
        html.H5('Escalation'),
        _tool_key_field(
            {'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': 'escalation.origin_tool_key'},
            'Origin tool key',
            escalation.get('origin_tool_key'),
        ),
        html.Button(
            'Add escalation step',
            id={'type': STEP_ADD_TYPE, 'rule': rule_index},
            n_clicks=0,
            type='button',
        ),
    ]
    for step_index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            continue
        children.append(
            html.Fieldset(
                [
                    html.Legend(f'Step {step_index + 1}'),
                    html.Button(
                        'Remove step',
                        id={
                            'type': STEP_REMOVE_TYPE,
                            'rule': rule_index,
                            'step': step_index,
                        },
                        n_clicks=0,
                        type='button',
                    ),
                    _step_number_field(
                        rule_index,
                        step_index,
                        'step_order',
                        'Step order',
                        raw_step.get('step_order'),
                    ),
                    _tool_key_field(
                        {
                            'type': STEP_FIELD_TYPE,
                            'rule': rule_index,
                            'step': step_index,
                            'field': 'target_tool_key',
                        },
                        'Target tool key',
                        raw_step.get('target_tool_key'),
                    ),
                    _step_bool_field(
                        rule_index,
                        step_index,
                        'is_enabled',
                        'Enabled',
                        raw_step.get('is_enabled'),
                    ),
                    _step_number_field(
                        rule_index,
                        step_index,
                        'wait_minutes_from_previous_step',
                        'Wait minutes from previous step',
                        raw_step.get('wait_minutes_from_previous_step'),
                    ),
                ]
            )
        )
    return html.Section(children)


def _visual_targets_editor(
    rule_index: int,
    targets: list[object],
    reference_document: dict[str, object] | None,
) -> object:
    children: list[object] = [
        html.H5('Visual targets'),
        html.Button(
            'Add visual target',
            id={'type': TARGET_ADD_TYPE, 'rule': rule_index},
            n_clicks=0,
            type='button',
        ),
    ]
    for target_index, raw_target in enumerate(targets):
        if not isinstance(raw_target, dict):
            continue
        tool_key = _string(raw_target.get('tool_key'))
        component_keys = _string_list(raw_target.get('component_keys'))
        components = component_suggestions(reference_document, tool_key)
        subcomponents = subcomponent_suggestions(
            reference_document,
            tool_key,
            component_keys,
        )
        component_list_id = f'alarm-configuration-component-options-{rule_index}-{target_index}'
        owner_list_id = f'alarm-configuration-owner-options-{rule_index}-{target_index}'
        subcomponent_list_id = (
            f'alarm-configuration-subcomponent-options-{rule_index}-{target_index}'
        )
        target_children: list[object] = [
            html.Legend(f'Visual target {target_index + 1}'),
            html.Button(
                'Remove target',
                id={
                    'type': TARGET_REMOVE_TYPE,
                    'rule': rule_index,
                    'target': target_index,
                },
                n_clicks=0,
                type='button',
            ),
            _tool_key_field(
                {
                    'type': TARGET_FIELD_TYPE,
                    'rule': rule_index,
                    'target': target_index,
                    'field': 'tool_key',
                },
                'Tool key',
                tool_key,
            ),
            _target_enum_field(
                rule_index,
                target_index,
                'process_projection_mode',
                'Process projection mode',
                raw_target.get('process_projection_mode'),
                ProcessAlarmProjectionMode,
                clearable=True,
            ),
            html.Datalist(
                id=component_list_id,
                children=[
                    html.Option(value=item['value'], label=item['label']) for item in components
                ],
            ),
            html.Datalist(
                id=owner_list_id,
                children=[
                    html.Option(value=value)
                    for value in sorted({item['owner_component_key'] for item in subcomponents})
                ],
            ),
            html.Datalist(
                id=subcomponent_list_id,
                children=[
                    html.Option(
                        value=item['subcomponent_key'],
                        label=f'{item["display_name"]} ({item["owner_component_key"]})',
                    )
                    for item in subcomponents
                ],
            ),
            html.H6('Components'),
        ]
        for component_index, component_key in enumerate(component_keys):
            target_children.append(
                html.Div(
                    [
                        dcc.Input(
                            id={
                                'type': COMPONENT_FIELD_TYPE,
                                'rule': rule_index,
                                'target': target_index,
                                'component': component_index,
                            },
                            type='text',
                            value=component_key,
                            list=component_list_id,
                            debounce=True,
                        ),
                        html.Button(
                            'Remove',
                            id={
                                'type': COMPONENT_REMOVE_TYPE,
                                'rule': rule_index,
                                'target': target_index,
                                'component': component_index,
                            },
                            n_clicks=0,
                            type='button',
                        ),
                    ]
                )
            )
        target_children.append(
            html.Button(
                'Add component',
                id={
                    'type': COMPONENT_ADD_TYPE,
                    'rule': rule_index,
                    'target': target_index,
                },
                n_clicks=0,
                type='button',
            )
        )
        target_children.append(html.H6('Subcomponents'))
        raw_subcomponents = _list(raw_target.get('subcomponents'))
        for subcomponent_index, raw_subcomponent in enumerate(raw_subcomponents):
            if not isinstance(raw_subcomponent, dict):
                continue
            target_children.append(
                html.Div(
                    [
                        dcc.Input(
                            id={
                                'type': SUBCOMPONENT_FIELD_TYPE,
                                'rule': rule_index,
                                'target': target_index,
                                'subcomponent': subcomponent_index,
                                'field': 'owner_component_key',
                            },
                            type='text',
                            value=raw_subcomponent.get('owner_component_key'),
                            list=owner_list_id,
                            debounce=True,
                            placeholder='Owner component key',
                        ),
                        dcc.Input(
                            id={
                                'type': SUBCOMPONENT_FIELD_TYPE,
                                'rule': rule_index,
                                'target': target_index,
                                'subcomponent': subcomponent_index,
                                'field': 'subcomponent_key',
                            },
                            type='text',
                            value=raw_subcomponent.get('subcomponent_key'),
                            list=subcomponent_list_id,
                            debounce=True,
                            placeholder='Subcomponent key',
                        ),
                        html.Button(
                            'Remove',
                            id={
                                'type': SUBCOMPONENT_REMOVE_TYPE,
                                'rule': rule_index,
                                'target': target_index,
                                'subcomponent': subcomponent_index,
                            },
                            n_clicks=0,
                            type='button',
                        ),
                    ]
                )
            )
        target_children.append(
            html.Button(
                'Add subcomponent',
                id={
                    'type': SUBCOMPONENT_ADD_TYPE,
                    'rule': rule_index,
                    'target': target_index,
                },
                n_clicks=0,
                type='button',
            )
        )
        children.append(html.Fieldset(target_children))
    return html.Section(children)


def _message_editor(message_index: int, message: dict[str, object]) -> object:
    scope = message.get('scope')
    override = message.get('deactivation_override')
    override_mapping = _mapping(override) if isinstance(override, dict) else None
    title = _string(message.get('message_key')) or f'Message {message_index + 1}'
    children: list[object] = [
        html.Legend(title),
        html.Button(
            'Remove message',
            id={'type': MESSAGE_REMOVE_TYPE, 'message': message_index},
            n_clicks=0,
            type='button',
        ),
        _message_text_field(
            message_index, 'message_key', 'Message key', message.get('message_key')
        ),
        _message_enum_field(message_index, 'scope', 'Scope', scope, ('GLOBAL', 'FAMILY')),
    ]
    if scope == 'FAMILY':
        children.append(
            _message_text_field(
                message_index,
                'family_key',
                'Family key',
                message.get('family_key'),
            )
        )
    children.extend(
        [
            _message_text_field(
                message_index,
                'display_text',
                'Display text',
                message.get('display_text'),
            ),
            _message_bool_field(
                message_index,
                'is_active',
                'Active',
                message.get('is_active'),
            ),
            _message_bool_field(
                message_index,
                'deactivation_override.present',
                'Deactivation override',
                override_mapping is not None,
            ),
        ]
    )
    if override_mapping is not None:
        children.extend(
            [
                _message_bool_field(
                    message_index,
                    'deactivation_override.enabled',
                    'Override enabled',
                    override_mapping.get('enabled'),
                ),
                _message_number_field(
                    message_index,
                    'deactivation_override.max_duration_hours',
                    'Override max duration hours',
                    override_mapping.get('max_duration_hours'),
                ),
                _message_bool_field(
                    message_index,
                    'deactivation_override.approval_required',
                    'Override approval required',
                    override_mapping.get('approval_required'),
                ),
            ]
        )
    return html.Fieldset(children)


def _group(title: str, children: list[object]) -> object:
    return html.Fieldset([html.Legend(title), *children])


def _text_field(rule_index: int, field: str, label: str, value: object) -> object:
    return _labeled(
        label,
        dcc.Input(
            id={'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': field},
            type='text',
            value=value if isinstance(value, str) else '' if value is None else str(value),
            debounce=True,
        ),
    )


def _tool_key_field(component_id: object, label: str, value: object) -> object:
    return _labeled(
        label,
        dcc.Input(
            id=component_id,
            type='text',
            value=value if isinstance(value, str) else '',
            list=TOOL_DATALIST_ID,
            debounce=True,
        ),
    )


def _number_field(rule_index: int, field: str, label: str, value: object) -> object:
    return _labeled(
        label,
        dcc.Input(
            id={'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': field},
            type='number',
            value=value,
            step=1,
            debounce=True,
        ),
    )


def _bool_field(rule_index: int, field: str, label: str, value: object) -> object:
    return _dropdown_field(
        rule_index,
        field,
        label,
        value,
        [
            {'label': 'Yes', 'value': True},
            {'label': 'No', 'value': False},
        ],
        clearable=True,
    )


def _enum_field(
    rule_index: int,
    field: str,
    label: str,
    value: object,
    enum_type: object,
) -> object:
    options = [{'label': item.value, 'value': item.value} for item in enum_type]
    return _dropdown_field(rule_index, field, label, value, options, clearable=True)


def _multi_enum_field(
    rule_index: int,
    field: str,
    label: str,
    value: object,
    enum_type: object,
) -> object:
    options = [{'label': item.value, 'value': item.value} for item in enum_type]
    return _dropdown_field(
        rule_index,
        field,
        label,
        _string_list(value),
        options,
        multi=True,
    )


def _dropdown_field(
    rule_index: int,
    field: str,
    label: str,
    value: object,
    options: list[dict[str, object]],
    *,
    multi: bool = False,
    clearable: bool = False,
) -> object:
    return _labeled(
        label,
        dcc.Dropdown(
            id={'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': field},
            options=options,
            value=value,
            multi=multi,
            clearable=clearable,
            debounce=multi,
        ),
    )


def _step_number_field(
    rule_index: int,
    step_index: int,
    field: str,
    label: str,
    value: object,
) -> object:
    return _labeled(
        label,
        dcc.Input(
            id={
                'type': STEP_FIELD_TYPE,
                'rule': rule_index,
                'step': step_index,
                'field': field,
            },
            type='number',
            value=value,
            step=1,
            debounce=True,
        ),
    )


def _step_bool_field(
    rule_index: int,
    step_index: int,
    field: str,
    label: str,
    value: object,
) -> object:
    return _labeled(
        label,
        dcc.Dropdown(
            id={
                'type': STEP_FIELD_TYPE,
                'rule': rule_index,
                'step': step_index,
                'field': field,
            },
            options=[
                {'label': 'Yes', 'value': True},
                {'label': 'No', 'value': False},
            ],
            value=value,
            clearable=True,
        ),
    )


def _target_enum_field(
    rule_index: int,
    target_index: int,
    field: str,
    label: str,
    value: object,
    enum_type: object,
    *,
    clearable: bool,
) -> object:
    return _labeled(
        label,
        dcc.Dropdown(
            id={
                'type': TARGET_FIELD_TYPE,
                'rule': rule_index,
                'target': target_index,
                'field': field,
            },
            options=[{'label': item.value, 'value': item.value} for item in enum_type],
            value=value,
            clearable=clearable,
        ),
    )


def _message_text_field(message_index: int, field: str, label: str, value: object) -> object:
    return _labeled(
        label,
        dcc.Input(
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            type='text',
            value=value if isinstance(value, str) else '',
            debounce=True,
        ),
    )


def _message_number_field(
    message_index: int,
    field: str,
    label: str,
    value: object,
) -> object:
    return _labeled(
        label,
        dcc.Input(
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            type='number',
            value=value,
            step=1,
            debounce=True,
        ),
    )


def _message_bool_field(
    message_index: int,
    field: str,
    label: str,
    value: object,
) -> object:
    return _labeled(
        label,
        dcc.Dropdown(
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            options=[
                {'label': 'Yes', 'value': True},
                {'label': 'No', 'value': False},
            ],
            value=value,
            clearable=True,
        ),
    )


def _message_enum_field(
    message_index: int,
    field: str,
    label: str,
    value: object,
    values: tuple[str, ...],
) -> object:
    return _labeled(
        label,
        dcc.Dropdown(
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            options=[{'label': item, 'value': item} for item in values],
            value=value,
            clearable=True,
        ),
    )


def _labeled(label: str, control: object) -> object:
    return html.Label([html.Span(label), control])


def _message_options(
    messages: list[object],
    family_key: str,
    selected: list[object],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_message in messages:
        if not isinstance(raw_message, dict):
            continue
        message_key = _string(raw_message.get('message_key'))
        scope = raw_message.get('scope')
        message_family = _string(raw_message.get('family_key'))
        if not message_key:
            continue
        if scope == 'GLOBAL' or (scope == 'FAMILY' and message_family == family_key):
            options.append({'label': message_key, 'value': message_key})
            seen.add(message_key)
    for item in selected:
        if isinstance(item, str) and item not in seen:
            options.append({'label': f'{item} (unresolved)', 'value': item})
    return options


def _special_condition_options(
    rules: list[object],
    family_key: str,
    priority_group: str,
    selected: list[object],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_rule in rules:
        if not isinstance(raw_rule, dict) or raw_rule.get('is_special_condition') is not True:
            continue
        identity = _mapping(raw_rule.get('identity'))
        if _string(identity.get('family_key')) != family_key:
            continue
        if _string(raw_rule.get('priority_group')) != priority_group:
            continue
        canonical = _canonical_identity(identity)
        if not canonical:
            continue
        label = _string(raw_rule.get('display_name')) or canonical
        options.append({'label': f'{label} ({canonical})', 'value': canonical})
        seen.add(canonical)
    for item in _identity_values(selected):
        if item not in seen:
            options.append({'label': f'{item} (unresolved)', 'value': item})
    return options


def _identity_values(value: object) -> list[str]:
    values: list[str] = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        canonical = _canonical_identity(item)
        if canonical:
            values.append(canonical)
    return values


def _canonical_identity(value: Mapping[str, object]) -> str:
    family_key = _string(value.get('family_key'))
    alarm_key = _string(value.get('alarm_key'))
    if not family_key or not alarm_key:
        return ''
    return f'{family_key}/{alarm_key}'


def _parameters_text(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string(value: object) -> str:
    return value if isinstance(value, str) else ''


def _string_list(value: object) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str)]
