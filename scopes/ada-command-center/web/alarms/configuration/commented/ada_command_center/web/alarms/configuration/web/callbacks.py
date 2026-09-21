# Callbacks del modo documental de Alarm Configuration.
# Toda entrada se normaliza mediante AlarmConfiguration antes de entrar al workspace.
# El revision hash permite que Manager detecte cambios del editor de forma determinista.
from __future__ import annotations

import base64
import json
from binascii import Error as BinasciiError

from dash import Input, Output, State, ctx, html, no_update

from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationValidationError
from ada_command_center.web.alarms.configuration.models import AlarmConfiguration
from ada_command_center.web.alarms.configuration.web.ids import (
    DOCUMENT_EDITOR_ID,
    DOCUMENT_STATUS_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    MOUNT_STORE_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.workspace import ManagerWorkspace, build_workspace_revision


def register_alarm_configuration_admin_callbacks(
    app: object,
    context: AlarmConfigurationAdminWebContext,
) -> None:
    @app.callback(
        Output(DOCUMENT_EDITOR_ID, 'value'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        try:
            payload = context.workspace_payload_reader(draft_data)
            configuration = (
                AlarmConfiguration(rules=(), messages=())
                if payload is None
                else AlarmConfiguration.from_document(dict(payload))
            )
            return _format_configuration(configuration)
        except Exception:
            return _format_configuration(AlarmConfiguration(rules=(), messages=()))

    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(DOCUMENT_EDITOR_ID, 'value'),
        prevent_initial_call=True,
    )
    def track_editor_revision(document_text: str | None):
        try:
            configuration = _configuration(document_text)
            return build_workspace_revision(configuration.to_document())
        except Exception:
            return None

    @app.callback(
        Output(DOCUMENT_STATUS_ID, 'children'),
        Input(DOCUMENT_EDITOR_ID, 'value'),
    )
    def render_document_status(document_text: str | None):
        try:
            configuration = _configuration(document_text)
        except Exception as error:
            return _error(str(error))
        return _summary(configuration)

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(DOCUMENT_EDITOR_ID, 'value', allow_duplicate=True),
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
        return document, _format_configuration(configuration), _success('JSON imported into draft.')

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(DOCUMENT_EDITOR_ID, 'value'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        document_text: str | None,
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
            configuration = _configuration(document_text)
            document = context.workspace_payload_writer(
                current_draft,
                configuration.to_document(),
            )
            workspace = ManagerWorkspace.from_document(document)
            if editor_revision != workspace.revision:
                raise ManagerProjectionError(
                    'Alarm Configuration editor revision changed before saving the draft'
                )
        except (AlarmConfigurationValidationError, ManagerProjectionError, ValueError) as error:
            return no_update, no_update, _error(str(error))
        return document, document, _success('Draft saved in this browser.')


def _configuration(document_text: str | None) -> AlarmConfiguration:
    if not isinstance(document_text, str) or not document_text.strip():
        raise ValueError('Alarm Configuration document must not be empty')
    try:
        document = json.loads(document_text)
    except json.JSONDecodeError as error:
        raise ValueError('Alarm Configuration document is not valid JSON') from error
    if not isinstance(document, dict):
        raise ValueError('Alarm Configuration document root must be an object')
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


def _format_configuration(configuration: AlarmConfiguration) -> str:
    return json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _summary(configuration: AlarmConfiguration) -> object:
    return html.Div(
        [
            html.Strong('Valid document'),
            html.Span(f'Rules: {len(configuration.rules)}'),
            html.Span(
                f'Active rules: {sum(rule.is_active for rule in configuration.rules)}'
            ),
            html.Span(f'Messages: {len(configuration.messages)}'),
        ]
    )


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


def _click_is_real(value: int | None) -> bool:
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
