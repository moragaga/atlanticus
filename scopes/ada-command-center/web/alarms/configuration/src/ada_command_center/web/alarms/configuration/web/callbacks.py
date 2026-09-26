from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmConfigurationValidationError,
)
from ada_command_center.domain.tools import ToolDependencyManifest
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
from ada_command_center.web.alarms.configuration.web.diagnostics import (
    authoring_issues,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    AUTHORING_STORE_ID,
    COMPONENT_ADD_TYPE,
    COMPONENT_FIELD_TYPE,
    COMPONENT_REMOVE_TYPE,
    DOCUMENT_STATUS_ID,
    FAMILY_NAV_STORE_ID,
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
    MODAL_BODY_ID,
    MODAL_SAVE_BUTTON_ID,
    MODAL_SAVE_RESULT_ID,
    MODAL_TITLE_ID,
    MODAL_WRAPPER_ID,
    MOUNT_STORE_ID,
    PARAMETER_ADD_TYPE,
    PARAMETER_FIELD_TYPE,
    PARAMETER_REMOVE_TYPE,
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
from ada_command_center.web.alarms.configuration.web.import_review import (
    can_confirm,
    inspect_import,
    revision_warning,
)
from ada_command_center.web.alarms.configuration.web.layout import (
    build_active_alarm_editor,
    build_structured_editors,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from ada_command_center.web.alarms.configuration.web.parameters import (
    add_parameter,
    remove_parameter,
    set_parameter_field,
)
from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.workspace import ManagerWorkspace, build_workspace_revision


def register_alarm_configuration_admin_callbacks(
    app: object,
    context: AlarmConfigurationAdminWebContext,
) -> None:
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
            return None, html.Small('El catálogo de herramientas no está configurado.')
        try:
            catalog = context.tool_reference_provider()
        except Exception as error:
            return None, _error(f'No se pudo consultar el catálogo de herramientas: {error}')
        if catalog is None:
            return None, html.Small('No hay un catálogo de herramientas confirmado.')
        return tool_reference_catalog_to_document(catalog), None

    @app.callback(
        Output(RULES_EDITOR_ID, 'children'),
        Output(MESSAGES_EDITOR_ID, 'children'),
        Output(MODAL_TITLE_ID, 'children'),
        Output(MODAL_BODY_ID, 'children'),
        Output(MODAL_WRAPPER_ID, 'hidden'),
        Input(AUTHORING_STORE_ID, 'data'),
        Input(TOOL_REFERENCE_STORE_ID, 'data'),
        Input(FAMILY_NAV_STORE_ID, 'data'),
    )
    def render_editors(
        authoring_document: dict[str, object] | None,
        reference_document: dict[str, object] | None,
        navigation: dict[str, object] | None,
    ):
        listing, messages = build_structured_editors(
            authoring_document, reference_document, navigation
        )
        document = authoring_document or empty_authoring_document()
        title, details = build_active_alarm_editor(document, reference_document, navigation)
        return listing, messages, title, details, details is None

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
        issues = authoring_issues(authoring_document)
        return _authoring_feedback(issues) if issues else None

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
        Input({'type': PARAMETER_FIELD_TYPE, 'rule': ALL, 'parameter': ALL, 'field': ALL}, 'value'),
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
        _parameter_values: list[object],
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
            elif component_type == PARAMETER_FIELD_TYPE:
                updated = set_parameter_field(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['parameter']),
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
        Input({'type': PARAMETER_ADD_TYPE, 'rule': ALL}, 'n_clicks'),
        Input({'type': PARAMETER_REMOVE_TYPE, 'rule': ALL, 'parameter': ALL}, 'n_clicks'),
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
        _add_parameter_clicks: list[int | None],
        _remove_parameter_clicks: list[int | None],
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
            if component_type == PARAMETER_ADD_TYPE:
                return add_parameter(current_document, int(component_id['rule']))
            if component_type == PARAMETER_REMOVE_TYPE:
                return remove_parameter(
                    current_document,
                    int(component_id['rule']),
                    int(component_id['parameter']),
                )
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
        Output(IMPORT_REVIEW_STORE_ID, 'data'),
        Output(IMPORT_RESULT_ID, 'children'),
        Input(IMPORT_UPLOAD_ID, 'contents'),
        State(IMPORT_UPLOAD_ID, 'filename'),
        prevent_initial_call=True,
    )
    def inspect_import_file(contents: str | None, filename: str | None):
        if contents is None:
            return no_update, no_update
        if not context.can_manage():
            return no_update, _error('No tienes permiso para importar configuraciones.')
        try:
            preview = inspect_import(contents, filename)
            configuration = AlarmConfiguration.from_document(preview['configuration'])
            if isinstance(preview.get('tool_dependencies'), dict):
                dependency = ToolDependencyManifest.from_document(preview['tool_dependencies'])
                if dependency.revision != preview['tool_revision']:
                    raise ValueError('La revisión Tool incluida no coincide con sus dependencias.')
            preview['configuration'] = configuration.to_document()
            preview.pop('tool_dependencies', None)
        except (ValueError, TypeError, AlarmConfigurationValidationError) as error:
            return None, _error(str(error))
        return preview, no_update

    @app.callback(
        Output(IMPORT_REVIEW_MODAL_ID, 'hidden'),
        Output(IMPORT_REVIEW_CONTENT_ID, 'children'),
        Output(IMPORT_REVIEW_CONFIRM_ID, 'disabled'),
        Input(IMPORT_REVIEW_STORE_ID, 'data'),
        Input(TOOL_REFERENCE_STORE_ID, 'data'),
    )
    def render_import_review(
        review: dict[str, object] | None, reference_document: dict[str, object] | None
    ):
        if not isinstance(review, dict):
            return True, None, True
        current = (
            reference_document.get('catalog_revision')
            if isinstance(reference_document, dict)
            else None
        )
        warning = revision_warning(review, current)
        source_revision = review.get('tool_revision')
        panel = html.Div(
            [
                html.Div([html.Strong('Archivo'), html.Span(str(review.get('filename')))]),
                html.Div([html.Strong('Tipo'), html.Span(str(review.get('kind')))]),
                html.Div(
                    [
                        html.Strong('Revisión Tool actual'),
                        html.Code(current if isinstance(current, str) else 'No disponible'),
                    ]
                ),
                html.Div(
                    [
                        html.Strong('Revisión Tool del archivo'),
                        html.Code(
                            source_revision if isinstance(source_revision, str) else 'No incluida'
                        ),
                    ]
                ),
                html.P(warning, className='alarm-guided__notice')
                if warning
                else html.P(
                    'Revisión Tool coincidente. La publicación requiere validación propia.',
                    className='alarm-guided__tip',
                ),
            ],
            className='alarm-admin__import-review',
        )
        return False, panel, not can_confirm(review, current)

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(AUTHORING_STORE_ID, 'data', allow_duplicate=True),
        Output(IMPORT_REVIEW_STORE_ID, 'data', allow_duplicate=True),
        Output(IMPORT_RESULT_ID, 'children', allow_duplicate=True),
        Input(IMPORT_REVIEW_CONFIRM_ID, 'n_clicks'),
        Input(IMPORT_REVIEW_CANCEL_ID, 'n_clicks'),
        State(IMPORT_REVIEW_STORE_ID, 'data'),
        State(TOOL_REFERENCE_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def confirm_import(_confirm_clicks, _cancel_clicks, review, references, current_draft):
        if not _click_is_real(_triggered_value()):
            return no_update, no_update, no_update, no_update
        if ctx.triggered_id == IMPORT_REVIEW_CANCEL_ID:
            return no_update, no_update, None, no_update
        if ctx.triggered_id != IMPORT_REVIEW_CONFIRM_ID or not isinstance(review, dict):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, no_update, _error('No tienes permiso para importar.')
        current = references.get('catalog_revision') if isinstance(references, dict) else None
        if not can_confirm(review, current):
            return (
                no_update,
                no_update,
                no_update,
                _error('La revisión Tool del archivo no coincide.'),
            )
        try:
            configuration = AlarmConfiguration.from_document(review['configuration'])
            document = context.workspace_payload_writer(current_draft, configuration.to_document())
        except (
            AlarmConfigurationValidationError,
            ManagerProjectionError,
            ValueError,
            TypeError,
        ) as error:
            return no_update, no_update, no_update, _error(str(error))
        return (
            document,
            configuration.to_document(),
            None,
            _success('JSON importado al borrador en edición.'),
        )

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Output(MODAL_SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(MODAL_SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(AUTHORING_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        modal_clicks: int | None,
        authoring_document: dict[str, object] | None,
        current_draft: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not _save_draft_click_is_real(
            ctx.triggered_id,
            content_clicks=content_clicks,
            workflow_clicks=workflow_clicks,
            modal_clicks=modal_clicks,
            workflow_id=context.draft_save_action_id,
        ):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            error = _error('No tienes permiso para guardar cambios.')
            return no_update, no_update, error, error
        issues = authoring_issues(authoring_document)
        if issues:
            feedback = _authoring_feedback(issues)
            return no_update, no_update, feedback, feedback
        try:
            configuration = _configuration(authoring_document)
            if current_draft is not None:
                expected_editor_revision = _editor_revision(configuration, current_draft)
                if editor_revision != expected_editor_revision:
                    raise ManagerProjectionError(
                        'Alarm Configuration editor revision changed before saving the draft'
                    )
            document = context.workspace_payload_writer(current_draft, configuration.to_document())
        except (AlarmConfigurationValidationError, ManagerProjectionError, ValueError) as error:
            feedback = _error(str(error))
            return no_update, no_update, feedback, feedback
        feedback = _success('Borrador guardado en este navegador.')
        return document, document, feedback, feedback


def _readiness_feedback(hints: tuple[str, ...]) -> object:
    return html.Div(
        [
            html.Strong('Observaciones para Materialization'),
            html.Ul([html.Li(hint) for hint in hints]),
        ],
        className='atlanticus-manager__message atlanticus-manager__message--warning',
    )


def _authoring_feedback(issues: tuple[str, ...], hints: tuple[str, ...] = ()) -> object:
    children = [
        html.Strong('Configuración en edición'),
        html.P('Completa estos datos antes de guardar o validar:'),
        html.Ul([html.Li(issue) for issue in issues[:5]]),
    ]
    if len(issues) > 5:
        children.append(
            html.Details(
                [
                    html.Summary(f'Ver {len(issues) - 5} observaciones restantes'),
                    html.Ul([html.Li(issue) for issue in issues[5:]]),
                ]
            )
        )
    if hints:
        children.append(_readiness_feedback(hints))
    return html.Div(
        children,
        className='atlanticus-manager__message atlanticus-manager__message--warning',
    )


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
    modal_clicks: int | None = None,
) -> bool:
    if trigger == SAVE_BUTTON_ID:
        return _click_is_real(content_clicks)
    if trigger == MODAL_SAVE_BUTTON_ID:
        return _click_is_real(modal_clicks)
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
