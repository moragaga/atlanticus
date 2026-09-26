from __future__ import annotations

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
from ada_command_center.web.alarms.configuration.web.families import initial_navigation
from ada_command_center.web.alarms.configuration.web.family_panel import (
    build_active_editor,
    build_family_panel,
)
from ada_command_center.web.alarms.configuration.web.guided_rule import build_rule_section
from ada_command_center.web.alarms.configuration.web.ids import (
    ADD_MESSAGE_BUTTON_ID,
    ADD_RULE_BUTTON_ID,
    AUTHORING_STORE_ID,
    CANCEL_FAMILY_CREATE_FOOTER_ID,
    CANCEL_FAMILY_CREATE_ID,
    CLOSE_EDITOR_ID,
    COMPONENT_ADD_TYPE,
    COMPONENT_FIELD_TYPE,
    COMPONENT_REMOVE_TYPE,
    CREATE_FAMILY_ID,
    DOCUMENT_STATUS_ID,
    FAMILY_ACTION_RESULT_ID,
    FAMILY_CREATE_PANEL_ID,
    FAMILY_NAV_STORE_ID,
    FAMILY_NEW_KEY_ID,
    IMPORT_RESULT_ID,
    IMPORT_REVIEW_CANCEL_ID,
    IMPORT_REVIEW_CONFIRM_ID,
    IMPORT_REVIEW_CONTENT_ID,
    IMPORT_REVIEW_MODAL_ID,
    IMPORT_REVIEW_STORE_ID,
    IMPORT_UPLOAD_ID,
    MESSAGE_FIELD_TYPE,
    MESSAGE_REMOVE_TYPE,
    MESSAGES_EDITOR_ID,
    MODAL_BACK_ID,
    MODAL_BODY_ID,
    MODAL_SAVE_BUTTON_ID,
    MODAL_SAVE_RESULT_ID,
    MODAL_TITLE_ID,
    MODAL_WRAPPER_ID,
    MOUNT_STORE_ID,
    OPEN_FAMILY_CREATE_ID,
    PROJECTION_NAME_ID,
    RULE_FIELD_TYPE,
    RULE_REMOVE_TYPE,
    RULES_EDITOR_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SHOW_FAMILIES_ID,
    SHOW_GLOBAL_MESSAGES_ID,
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
from ada_command_center.web.alarms.configuration.web.labels import (
    field_help,
    field_label,
    value_label,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from ada_command_center.web.alarms.configuration.web.parameters import parameter_editor
from ada_command_center.web.alarms.configuration.web.select_style import dash_select_style


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
            dcc.Store(id=IMPORT_REVIEW_STORE_ID, data=None, storage_type='memory'),
            dcc.Store(id=FAMILY_NAV_STORE_ID, data=initial_navigation(), storage_type='memory'),
            _runtime_context(context),
            html.Section(
                [
                    html.Div(id=TOOL_REFERENCE_STATUS_ID),
                    html.Div(id=DOCUMENT_STATUS_ID),
                ],
                className='alarm-admin__status',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3('Familias, reglas y mensajes'),
                                    html.P(
                                        'Administra los elementos de cada familia por separado.'
                                    ),
                                ],
                                className='alarm-admin__heading-copy',
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        '+ Nueva regla',
                                        id=ADD_RULE_BUTTON_ID,
                                        n_clicks=0,
                                        disabled=True,
                                        type='button',
                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                    ),
                                    html.Button(
                                        '+ Nuevo mensaje',
                                        id=ADD_MESSAGE_BUTTON_ID,
                                        n_clicks=0,
                                        disabled=True,
                                        type='button',
                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                    ),
                                    html.Button(
                                        '+ Nueva familia',
                                        id=OPEN_FAMILY_CREATE_ID,
                                        n_clicks=0,
                                        type='button',
                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                    ),
                                ],
                                className='alarm-admin__heading-actions',
                            ),
                        ],
                        className='alarm-admin__heading',
                    ),
                    html.Nav(
                        [
                            html.Button(
                                'Todas las familias',
                                id=SHOW_FAMILIES_ID,
                                n_clicks=0,
                                type='button',
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                            ),
                            html.Button(
                                'Mensajes globales',
                                id=SHOW_GLOBAL_MESSAGES_ID,
                                n_clicks=0,
                                type='button',
                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                            ),
                        ],
                        className='alarm-admin__navigation',
                    ),
                    html.Div(
                        [
                            html.Div(className='alarm-family__modal-backdrop'),
                            html.Div(
                                [
                                    html.Header(
                                        [
                                            html.Div(
                                                [
                                                    html.Small('ADMINISTRAR FAMILIAS'),
                                                    html.H3('Nueva familia'),
                                                ]
                                            ),
                                            html.Button(
                                                '×',
                                                id=CANCEL_FAMILY_CREATE_ID,
                                                type='button',
                                                n_clicks=0,
                                                className='atlanticus-ui-icon-button alarm-family__modal-close',
                                                **{'aria-label': 'Cerrar'},
                                            ),
                                        ],
                                        className='alarm-family__modal-header',
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                [
                                                    html.Span('Nombre o clave de la familia'),
                                                    dcc.Input(
                                                        id=FAMILY_NEW_KEY_ID,
                                                        type='text',
                                                        value='',
                                                        placeholder='Ej.: control-planta',
                                                        debounce=False,
                                                        className='form-control form-control-sm',
                                                    ),
                                                    html.Small(
                                                        'Se incorpora al documento con su primera regla o mensaje.'
                                                    ),
                                                ],
                                                className='alarm-admin__new-family-field',
                                            ),
                                            html.Div(
                                                id=FAMILY_ACTION_RESULT_ID,
                                                className='alarm-admin__family-result',
                                                role='status',
                                            ),
                                        ],
                                        className='alarm-admin__family-modal-body',
                                    ),
                                    html.Footer(
                                        [
                                            html.Button(
                                                'Cancelar',
                                                id=CANCEL_FAMILY_CREATE_FOOTER_ID,
                                                n_clicks=0,
                                                type='button',
                                                className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                            ),
                                            html.Button(
                                                'Crear familia',
                                                id=CREATE_FAMILY_ID,
                                                n_clicks=0,
                                                type='button',
                                                className='atlanticus-ui-button atlanticus-ui-button--primary',
                                            ),
                                        ],
                                        className='alarm-family__modal-footer',
                                    ),
                                ],
                                className='alarm-family__modal-dialog '
                                'alarm-family__modal-dialog--small',
                                role='dialog',
                                **{'aria-modal': 'true'},
                            ),
                        ],
                        id=FAMILY_CREATE_PANEL_ID,
                        className='alarm-family__modal',
                        hidden=True,
                    ),
                    html.Div(id=RULES_EDITOR_ID),
                    html.Div(id=MESSAGES_EDITOR_ID, hidden=True),
                    html.Div(
                        [
                            html.Div(className='alarm-family__modal-backdrop'),
                            html.Div(
                                [
                                    html.Header(
                                        [
                                            html.H3(id=MODAL_TITLE_ID),
                                            html.Button(
                                                '×',
                                                id=CLOSE_EDITOR_ID,
                                                n_clicks=0,
                                                type='button',
                                                className='atlanticus-ui-icon-button alarm-family__modal-close',
                                                **{'aria-label': 'Cerrar'},
                                            ),
                                        ],
                                        className='alarm-family__modal-header',
                                    ),
                                    html.Div(id=MODAL_BODY_ID, className='alarm-family__detail'),
                                    html.Footer(
                                        [
                                            html.Div(
                                                id=MODAL_SAVE_RESULT_ID,
                                                className='alarm-family__save-result',
                                                role='status',
                                            ),
                                            html.Div(
                                                [
                                                    html.Button(
                                                        'Volver',
                                                        id=MODAL_BACK_ID,
                                                        n_clicks=0,
                                                        type='button',
                                                        className='atlanticus-ui-button atlanticus-ui-button--secondary',
                                                    ),
                                                    html.Button(
                                                        'Guardar',
                                                        id=MODAL_SAVE_BUTTON_ID,
                                                        n_clicks=0,
                                                        type='button',
                                                        className='atlanticus-ui-button atlanticus-ui-button--primary',
                                                    ),
                                                ],
                                                className='alarm-family__modal-actions',
                                            ),
                                        ],
                                        className='alarm-family__modal-footer',
                                    ),
                                ],
                                className='alarm-family__modal-dialog',
                                role='dialog',
                                **{'aria-modal': 'true'},
                            ),
                        ],
                        id=MODAL_WRAPPER_ID,
                        className='alarm-family__modal',
                        hidden=True,
                    ),
                ],
                className='alarm-admin__section',
            ),
            html.Div(
                [
                    html.Div(className='alarm-family__modal-backdrop'),
                    html.Div(
                        [
                            html.Header(
                                [
                                    html.Div(
                                        [
                                            html.Small('CONFIGURACIÓN · IMPORTACIÓN'),
                                            html.H3('Revisar importación'),
                                        ]
                                    ),
                                    html.Button(
                                        '×',
                                        id=IMPORT_REVIEW_CANCEL_ID,
                                        n_clicks=0,
                                        type='button',
                                        className='atlanticus-ui-icon-button alarm-family__modal-close',
                                        **{'aria-label': 'Cerrar'},
                                    ),
                                ],
                                className='alarm-family__modal-header',
                            ),
                            html.Div(
                                id=IMPORT_REVIEW_CONTENT_ID,
                                className='alarm-admin__import-review-body',
                            ),
                            html.Footer(
                                [
                                    html.Button(
                                        'Confirmar importación',
                                        id=IMPORT_REVIEW_CONFIRM_ID,
                                        n_clicks=0,
                                        disabled=True,
                                        type='button',
                                        className='atlanticus-ui-button atlanticus-ui-button--primary',
                                    ),
                                ],
                                className='alarm-family__modal-footer',
                            ),
                        ],
                        className='alarm-family__modal-dialog alarm-family__modal-dialog--small',
                        role='dialog',
                        **{'aria-modal': 'true'},
                    ),
                ],
                id=IMPORT_REVIEW_MODAL_ID,
                className='alarm-family__modal',
                hidden=True,
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · alarmas'),
                            html.P('Guarda los cambios cuando completes los campos obligatorios.'),
                        ],
                        className='alarm-admin__heading-copy',
                    ),
                    html.Button(
                        'Guardar borrador',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                        className='atlanticus-ui-button atlanticus-ui-button--primary',
                    ),
                    html.Div(id=SAVE_RESULT_ID, className='alarm-admin__save-result'),
                ],
                className='alarm-admin__section alarm-admin__footer',
            ),
        ],
        className='ada-command-center-alarm-editor atlanticus-bootstrap alarm-admin',
    )


def build_structured_editors(
    authoring_document: dict[str, object] | None,
    reference_document: dict[str, object] | None,
    navigation: dict[str, object] | None = None,
) -> tuple[object, object]:
    document = authoring_document or empty_authoring_document()
    tools = tool_suggestions(reference_document)
    datalist = html.Datalist(
        id=TOOL_DATALIST_ID,
        children=[html.Option(value=item['value'], label=item['label']) for item in tools],
    )
    panel = build_family_panel(
        document,
        reference_document,
        navigation,
        rule_editor=_rule_editor,
        message_editor=_message_editor,
    )
    return html.Div([datalist, panel], className='alarm-family'), html.Div()


def build_active_alarm_editor(
    document: dict[str, object],
    references: dict[str, object] | None,
    navigation: dict[str, object] | None,
) -> tuple[str, object | None]:
    return build_active_editor(
        document,
        references,
        navigation,
        rule_editor=_rule_editor,
        message_editor=_message_editor,
    )


def _runtime_context(context: AlarmConfigurationAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ]
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ]
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=html.Button(
                            'Importar configuración',
                            type='button',
                            className='atlanticus-ui-button atlanticus-ui-button--secondary',
                        ),
                        accept='.json,application/json',
                        multiple=False,
                    ),
                    html.Span('El archivo se revisa antes de sustituir el borrador.'),
                    html.Div(id=IMPORT_RESULT_ID),
                ]
            ),
        ],
        className='alarm-admin__runtime',
    )


def _rule_editor(
    rule_index: int,
    rule: dict[str, object],
    rules: list[object],
    messages: list[object],
    reference_document: dict[str, object] | None,
    section: str = 'general',
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
    title = title or f'Regla {rule_index + 1}'
    message_options = _message_options(messages, family_key, _list(rule.get('message_keys')))
    special_options = _special_condition_options(
        rules,
        family_key,
        priority_group,
        _list(reappearance.get('special_conditions')),
    )
    return build_rule_section(
        [
            html.Legend(title),
            html.Button(
                'Eliminar regla',
                id={'type': RULE_REMOVE_TYPE, 'rule': rule_index},
                n_clicks=0,
                type='button',
            ),
            _group(
                'Identity and presentation',
                [
                    html.Div(
                        [html.Span('Familia'), html.Strong(family_key)],
                        className='alarm-admin__read-only',
                    ),
                    html.Div(
                        [
                            html.Span('Identificador automático'),
                            html.Code(identity.get('alarm_key') or 'Sin asignar'),
                        ],
                        className='alarm-admin__read-only',
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
                    parameter_editor(rule_index, rule),
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
        ],
        section=section,
        criticality=rule.get('criticality'),
        deactivation_enabled=deactivation.get('enabled'),
        targets=targets,
        references=reference_document,
    )


def _escalation_editor(
    rule_index: int,
    escalation: Mapping[str, object],
    steps: list[object],
) -> object:
    children: list[object] = [
        html.H5('Escalamiento'),
        _tool_key_field(
            {'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': 'escalation.origin_tool_key'},
            'Origin tool key',
            escalation.get('origin_tool_key'),
        ),
        html.Button(
            'Agregar destino',
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
                    html.Legend(f'Destino {step_index + 1}'),
                    html.Button(
                        'Eliminar destino',
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
        html.H5('Destinos visuales'),
        html.Button(
            'Agregar destino visual',
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
            html.Legend(f'Destino visual {target_index + 1}'),
            html.Button(
                'Eliminar destino visual',
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
            html.H6('Componentes'),
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
                            'Eliminar',
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
                'Agregar componente',
                id={
                    'type': COMPONENT_ADD_TYPE,
                    'rule': rule_index,
                    'target': target_index,
                },
                n_clicks=0,
                type='button',
            )
        )
        target_children.append(html.H6('Subcomponentes'))
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
                            placeholder='Componente propietario',
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
                            placeholder='Subcomponente',
                        ),
                        html.Button(
                            'Eliminar',
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
                'Agregar subcomponente',
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
    title = _string(message.get('message_key')) or f'Mensaje {message_index + 1}'
    children: list[object] = [
        html.Legend(title),
        html.Button(
            'Eliminar mensaje',
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
    return html.Fieldset(
        [html.Legend(field_label(title)), *children], className='alarm-guided__group'
    )


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
    return _labeled(
        label,
        dcc.RadioItems(
            id={'type': RULE_FIELD_TYPE, 'rule': rule_index, 'field': field},
            options=[{'label': 'Sí', 'value': True}, {'label': 'No', 'value': False}],
            value=value,
            className='alarm-admin__choices',
        ),
    )


def _enum_field(
    rule_index: int,
    field: str,
    label: str,
    value: object,
    enum_type: object,
) -> object:
    options = [{'label': value_label(item.value), 'value': item.value} for item in enum_type]
    return _dropdown_field(rule_index, field, label, value, options, clearable=True)


def _multi_enum_field(
    rule_index: int,
    field: str,
    label: str,
    value: object,
    enum_type: object,
) -> object:
    options = [{'label': value_label(item.value), 'value': item.value} for item in enum_type]
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
            className='alarm-admin__dropdown',
            style=dash_select_style(),
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
        dcc.RadioItems(
            id={'type': STEP_FIELD_TYPE, 'rule': rule_index, 'step': step_index, 'field': field},
            options=[{'label': 'Sí', 'value': True}, {'label': 'No', 'value': False}],
            value=value,
            className='alarm-admin__choices',
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
            className='alarm-admin__dropdown',
            style=dash_select_style(),
            id={
                'type': TARGET_FIELD_TYPE,
                'rule': rule_index,
                'target': target_index,
                'field': field,
            },
            options=[{'label': value_label(item.value), 'value': item.value} for item in enum_type],
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


def _message_bool_field(message_index: int, field: str, label: str, value: object) -> object:
    return _labeled(
        label,
        dcc.RadioItems(
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            options=[{'label': 'Sí', 'value': True}, {'label': 'No', 'value': False}],
            value=value,
            className='alarm-admin__choices',
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
            className='alarm-admin__dropdown',
            style=dash_select_style(),
            id={'type': MESSAGE_FIELD_TYPE, 'message': message_index, 'field': field},
            options=[{'label': value_label(item), 'value': item} for item in values],
            value=value,
            clearable=True,
        ),
    )


def _labeled(label: str, control: object) -> object:
    hint = field_help(label)
    shown = (
        html.Div(control, className='alarm-admin__dropdown-shell')
        if isinstance(control, dcc.Dropdown)
        else control
    )
    children = [html.Span(field_label(label)), shown]
    if hint is not None:
        children.append(html.Small(hint, className='alarm-guided__field-help'))
    return html.Label(children, className='alarm-guided__field')


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
            options.append({'label': f'{item} (no encontrado)', 'value': item})
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
            options.append({'label': f'{item} (no encontrado)', 'value': item})
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


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string(value: object) -> str:
    return value if isinstance(value, str) else ''


def _string_list(value: object) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str)]
