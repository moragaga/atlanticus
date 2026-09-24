# Orquestación de callbacks del editor estructurado.
# El AUTHORING_STORE representa el documento en edición y puede quedar inválido temporalmente.
# Las referencias Tool son ayuda visual; una falla del catálogo no invalida el draft.

from __future__ import annotations

import base64
import json
from binascii import Error as BinasciiError

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmConfigurationValidationError,
)
from ada_command_center.web.alarms.configuration.web.authoring import (
    add_component_key,
    add_escalation_step,
    add_subcomponent,
    add_visual_target,
    empty_authoring_document,
    remove_component_key,
    remove_escalation_step,
    remove_message,
    remove_rule,
    remove_subcomponent,
    remove_visual_target,
    set_component_key,
    set_escalation_step_field,
    set_message_field,
    set_rule_field,
    set_subcomponent_field,
    set_visual_target_field,
    tool_reference_catalog_to_document,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    AUTHORING_STORE_ID,
    COMPONENT_ADD_TYPE,
    COMPONENT_FIELD_TYPE,
    COMPONENT_REMOVE_TYPE,
    DOCUMENT_STATUS_ID,
    FAMILY_NAV_STORE_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    MESSAGE_FIELD_TYPE,
    MESSAGE_REMOVE_TYPE,
    MESSAGES_EDITOR_ID,
    MOUNT_STORE_ID,
    RULE_FIELD_TYPE,
    RULE_REMOVE_TYPE,
    RULES_EDITOR_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    STEP_ADD_TYPE,
    STEP_FIELD_TYPE,
    STEP_REMOVE_TYPE,
    SUBCOMPONENT_ADD_TYPE,
    SUBCOMPONENT_FIELD_TYPE,
    SUBCOMPONENT_REMOVE_TYPE,
    TARGET_ADD_TYPE,
    TARGET_FIELD_TYPE,
    TARGET_REMOVE_TYPE,
    TOOL_REFERENCE_STATUS_ID,
    TOOL_REFERENCE_STORE_ID,
)
from ada_command_center.web.alarms.configuration.web.layout import build_structured_editors
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.workspace import ManagerWorkspace, build_workspace_revision


def register_alarm_configuration_admin_callbacks(
    app: object,
    context: AlarmConfigurationAdminWebContext,
) -> None:
    # El Manager genérico es dueño de hidratar el workspace desde Source.
    # Este callback espera un cambio real del draft para no convertir el documento vacío
    # inicial del editor en trabajo local antes de que exista un ManagerWorkspace.
    @app.callback(
        Output(AUTHORING_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def load_browser_draft(draft_data: dict[str, object] | None):
        if draft_data is None:
            return empty_authoring_document()
        payload = context.workspace_payload_reader(draft_data)
        if payload is None:
            return empty_authoring_document()
        return AlarmConfiguration.from_document(dict(payload)).to_document()

    @app.callback(
        Output(TOOL_REFERENCE_STORE_ID, 'data'),
        Output(TOOL_REFERENCE_STATUS_ID, 'children'),
        Input(MOUNT_STORE_ID, 'data'),
    )
    def load_tool_references(_mounted: object):
        if context.tool_reference_provider is None:
            return None, html.Small('Tool catalog is not configured. Manual keys remain available.')
        try:
            catalog = context.tool_reference_provider()
        except Exception as error:
            return None, _error(f'Tool reference catalog is unavailable: {error}')
        if catalog is None:
            return (
                None,
                html.Small('Tool catalog has no current snapshot. Manual keys remain available.'),
            )
        document = tool_reference_catalog_to_document(catalog)
        return document, html.Small(f'Tool catalog revision: {catalog.catalog_revision}')

    @app.callback(
        Output(RULES_EDITOR_ID, 'children'),
        Output(MESSAGES_EDITOR_ID, 'children'),
        Input(AUTHORING_STORE_ID, 'data'),
        Input(TOOL_REFERENCE_STORE_ID, 'data'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
    )
    def render_editors(
        authoring_document: dict[str, object] | None,
        reference_document: dict[str, object] | None,
        navigation: dict[str, object] | None,
    ):
        return build_structured_editors(authoring_document, reference_document, navigation)

    # La revisión del editor sólo tiene significado cuando existe un workspace del Manager.
    # Sin esa base, una revisión del documento vacío bloquearía la hidratación automática.
    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(AUTHORING_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(
        authoring_document: dict[str, object] | None,
        draft_data: dict[str, object] | None,
    ):
        if draft_data is None:
            return None
        try:
            configuration = _configuration(authoring_document)
            return _editor_revision(configuration, draft_data)
        except Exception:
            return None

    @app.callback(
        Output(DOCUMENT_STATUS_ID, 'children'),
        Input(AUTHORING_STORE_ID, 'data'),
    )
    def render_document_status(authoring_document: dict[str, object] | None):
        try:
            configuration = _configuration(authoring_document)
        except Exception as error:
            return _error(str(error))
        return _summary(configuration)

    @app.callback(
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': RULE_FIELD_TYPE, 'rule': ALL, 'field': ALL}, 'value'),
        Input({'type': STEP_FIELD_TYPE, 'rule': ALL, 'step': ALL, 'field': ALL}, 'value'),
        Input({'type': TARGET_FIELD_TYPE, 'rule': ALL, 'target': ALL, 'field': ALL}, 'value'),
        Input(
            {'type': COMPONENT_FIELD_TYPE, 'rule': ALL, 'target': ALL, 'component': ALL},
            'value',
        ),
        Input(
            {
                'type': SUBCOMPONENT_FIELD_TYPE,
                'rule': ALL,
                'target': ALL,
                'subcomponent': ALL,
                'field': ALL,
            },
            'value',
        ),
        Input({'type': MESSAGE_FIELD_TYPE, 'message': ALL, 'field': ALL}, 'value'),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_authoring_fields(
        _rule_values: list[object],
        _step_values: list[object],
        _target_values: list[object],
        _component_values: list[object],
        _subcomponent_values: list[object],
        _message_values: list[object],
        current_document: dict[str, object] | None,
    ):
        component_id = ctx.triggered_id
        if not isinstance(component_id, dict) or current_document is None:
            return no_update
        field_value = _triggered_value()
        component_type = component_id.get('type')
        try:
            if component_type == RULE_FIELD_TYPE:
                updated = set_rule_field(
                    current_document,
                    int(component_id['rule']),
                    str(component_id['field']),
                    field_value,
                )
            elif component_type == STEP_FIELD_TYPE:
                updated = set_escalation_step_field(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['step']),
                    str(component_id['field']),
                    field_value,
                )
            elif component_type == TARGET_FIELD_TYPE:
                updated = set_visual_target_field(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                    str(component_id['field']),
                    field_value,
                )
            elif component_type == COMPONENT_FIELD_TYPE:
                updated = set_component_key(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                    int(component_id['component']),
                    field_value,
                )
            elif component_type == SUBCOMPONENT_FIELD_TYPE:
                updated = set_subcomponent_field(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                    int(component_id['subcomponent']),
                    str(component_id['field']),
                    field_value,
                )
            elif component_type == MESSAGE_FIELD_TYPE:
                updated = set_message_field(
                    current_document,
                    int(component_id['message']),
                    str(component_id['field']),
                    field_value,
                )
            else:
                return no_update
        except IndexError, KeyError, TypeError, ValueError:
            return no_update
        return no_update if updated == current_document else updated

    @app.callback(
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': RULE_REMOVE_TYPE, 'rule': ALL}, 'n_clicks'),
        Input({'type': MESSAGE_REMOVE_TYPE, 'message': ALL}, 'n_clicks'),
        Input({'type': STEP_ADD_TYPE, 'rule': ALL}, 'n_clicks'),
        Input({'type': STEP_REMOVE_TYPE, 'rule': ALL, 'step': ALL}, 'n_clicks'),
        Input({'type': TARGET_ADD_TYPE, 'rule': ALL}, 'n_clicks'),
        Input({'type': TARGET_REMOVE_TYPE, 'rule': ALL, 'target': ALL}, 'n_clicks'),
        Input({'type': COMPONENT_ADD_TYPE, 'rule': ALL, 'target': ALL}, 'n_clicks'),
        Input(
            {'type': COMPONENT_REMOVE_TYPE, 'rule': ALL, 'target': ALL, 'component': ALL},
            'n_clicks',
        ),
        Input({'type': SUBCOMPONENT_ADD_TYPE, 'rule': ALL, 'target': ALL}, 'n_clicks'),
        Input(
            {
                'type': SUBCOMPONENT_REMOVE_TYPE,
                'rule': ALL,
                'target': ALL,
                'subcomponent': ALL,
            },
            'n_clicks',
        ),
        State(AUTHORING_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_authoring_structure(
        _remove_rule_clicks: list[int | None],
        _remove_message_clicks: list[int | None],
        _add_step_clicks: list[int | None],
        _remove_step_clicks: list[int | None],
        _add_target_clicks: list[int | None],
        _remove_target_clicks: list[int | None],
        _add_component_clicks: list[int | None],
        _remove_component_clicks: list[int | None],
        _add_subcomponent_clicks: list[int | None],
        _remove_subcomponent_clicks: list[int | None],
        current_document: dict[str, object] | None,
    ):
        component_id = ctx.triggered_id
        if current_document is None or not _click_is_real(_triggered_value()):
            return no_update
        try:
            if not isinstance(component_id, dict):
                return no_update
            component_type = component_id.get('type')
            if component_type == RULE_REMOVE_TYPE:
                return remove_rule(current_document, int(component_id['rule']))
            if component_type == MESSAGE_REMOVE_TYPE:
                return remove_message(current_document, int(component_id['message']))
            if component_type == STEP_ADD_TYPE:
                return add_escalation_step(current_document, int(component_id['rule']))
            if component_type == STEP_REMOVE_TYPE:
                return remove_escalation_step(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['step']),
                )
            if component_type == TARGET_ADD_TYPE:
                return add_visual_target(current_document, int(component_id['rule']))
            if component_type == TARGET_REMOVE_TYPE:
                return remove_visual_target(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                )
            if component_type == COMPONENT_ADD_TYPE:
                return add_component_key(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                )
            if component_type == COMPONENT_REMOVE_TYPE:
                return remove_component_key(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                    int(component_id['component']),
                )
            if component_type == SUBCOMPONENT_ADD_TYPE:
                return add_subcomponent(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                )
            if component_type == SUBCOMPONENT_REMOVE_TYPE:
                return remove_subcomponent(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['target']),
                    int(component_id['subcomponent']),
                )
        except IndexError, KeyError, TypeError, ValueError:
            return no_update
        return no_update

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Output(IMPORT_RESULT_ID, 'children'),
        Input(IMPORT_UPLOAD_ID, 'contents'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def import_configuration(
        contents: str | None,
        current_draft: dict[str, object] | None,
    ):
        if contents is None:
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            configuration = _decode_import(contents)
            document = context.workspace_payload_writer(
                current_draft,
                configuration.to_document(),
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return document, configuration.to_document(), _success('JSON imported into draft.')

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(AUTHORING_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        authoring_document: dict[str, object] | None,
        current_draft: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not _save_draft_click_is_real(
            ctx.triggered_id,
            content_clicks=content_clicks,
            workflow_clicks=workflow_clicks,
            workflow_id=context.draft_save_action_id,
        ):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            configuration = _configuration(authoring_document)
            if current_draft is not None:
                expected_editor_revision = _editor_revision(configuration, current_draft)
                if editor_revision != expected_editor_revision:
                    raise ManagerProjectionError(
                        'Alarm Configuration editor revision changed before saving the draft'
                    )
            document = context.workspace_payload_writer(
                current_draft,
                configuration.to_document(),
            )
        except (AlarmConfigurationValidationError, ManagerProjectionError, ValueError) as error:
            return no_update, no_update, _error(str(error))
        return document, document, _success('Draft saved in this browser.')


# El sidecar Tools forma parte de ManagerWorkspace.revision, pero no del documento authored.
# Si rules/messages no cambiaron usamos la revisión completa del workspace. Si el usuario editó
# contenido, una revisión sólo del documento authored basta para detectar esa suciedad antes del Save.
def _editor_revision(
    configuration: AlarmConfiguration,
    draft_data: dict[str, object],
) -> str:
    workspace = ManagerWorkspace.from_document(draft_data)
    saved_configuration = AlarmConfiguration.from_document(dict(workspace.payload))
    if configuration == saved_configuration:
        return workspace.revision
    return build_workspace_revision(configuration.to_document())


def _configuration(authoring_document: dict[str, object] | None) -> AlarmConfiguration:
    document = (
        empty_authoring_document() if authoring_document is None else dict(authoring_document)
    )
    return AlarmConfiguration.from_document(document)


def _decode_import(contents: str) -> AlarmConfiguration:
    if ',' not in contents:
        raise ValueError('Alarm Configuration import payload is invalid')
    try:
        payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
        document = json.loads(payload.decode('utf-8'))
    except (BinasciiError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Alarm Configuration import is not valid JSON') from error
    if not isinstance(document, dict):
        raise ValueError('Alarm Configuration import root must be an object')
    return AlarmConfiguration.from_document(document)


def _summary(configuration: AlarmConfiguration) -> object:
    return html.Div(
        [
            html.Strong('Valid document'),
            html.Span(f'Rules: {len(configuration.rules)}'),
            html.Span(f'Active rules: {sum(rule.is_active for rule in configuration.rules)}'),
            html.Span(f'Messages: {len(configuration.messages)}'),
        ]
    )


def _triggered_value() -> object:
    if not ctx.triggered:
        return None
    return ctx.triggered[0].get('value')


def _save_draft_click_is_real(
    trigger: object,
    *,
    content_clicks: int | None,
    workflow_clicks: int | None,
    workflow_id: object,
) -> bool:
    if trigger == SAVE_BUTTON_ID:
        return _click_is_real(content_clicks)
    if isinstance(trigger, dict) and isinstance(workflow_id, dict):
        return dict(trigger) == dict(workflow_id) and _click_is_real(workflow_clicks)
    return trigger == workflow_id and _click_is_real(workflow_clicks)


def _click_is_real(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _success(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--success',
    )


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )
