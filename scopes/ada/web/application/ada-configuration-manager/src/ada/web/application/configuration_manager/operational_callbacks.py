from __future__ import annotations

from typing import TYPE_CHECKING

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.application.configuration_manager.operational_layout import (
    _position_options,
    _release_label,
    _revision,
    _status_label,
    modal_class,
    page_label,
    render_assignment_list,
    render_position_list,
)
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalAssignment,
    OperationalCatalog,
    assignment_source_key,
)
from atlanticus.web.manager import (
    ManagerProjectionError,
    ManagerWorkspace,
    build_workspace_revision,
)

if TYPE_CHECKING:
    from ada.web.application.configuration_manager.operational import (
        OperationalAssignmentContext,
        OperationalCatalogManagerWebContext,
    )


def register_operational_callbacks(
    app: object,
    catalog_context: OperationalCatalogManagerWebContext,
    assignment_context: OperationalAssignmentContext,
) -> None:
    _register_catalog_callbacks(app, catalog_context)
    _register_assignment_callbacks(app, assignment_context)


def _register_catalog_callbacks(
    app: object,
    context: OperationalCatalogManagerWebContext,
) -> None:
    @app.callback(
        Output(ids.CATALOG_EDITOR, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_catalog_manager_draft(draft_data: dict[str, object] | None):
        try:
            payload = context.workspace_payload_reader(draft_data)
            if payload is None:
                return no_update
            return OperationalCatalog.from_document(payload).to_document()
        except (ManagerProjectionError, ValueError):
            return no_update

    @app.callback(
        Output(context.editor_revision_store_id, 'data', allow_duplicate=True),
        Input(ids.CATALOG_EDITOR, 'data'),
        prevent_initial_call=True,
    )
    def track_catalog_revision(catalog_data: dict[str, object] | None):
        try:
            catalog = _catalog(catalog_data)
        except ValueError:
            return 'invalid'
        return build_workspace_revision(catalog.to_document())

    @app.callback(
        Output(context.result_id, 'children', allow_duplicate=True),
        Output(ids.CATALOG_SAVE_RESULT, 'children'),
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Input(ids.CATALOG_SAVE_DRAFT, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(ids.CATALOG_EDITOR, 'data'),
        State(context.draft_store_id, 'data'),
        State(context.editor_revision_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_catalog_draft(
        local_clicks: int | None,
        workflow_clicks: int | None,
        catalog_data: dict[str, object] | None,
        current_draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        if not (_click_is_real(local_clicks) or _click_is_real(workflow_clicks)):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            message = _message(
                'You do not have permission to manage the operational catalog.',
                error=True,
            )
            return message, message, no_update, no_update
        try:
            catalog = _catalog(catalog_data)
            document = context.workspace_payload_writer(
                current_draft_data,
                catalog.to_document(),
            )
            workspace = ManagerWorkspace.from_document(document)
            if editor_revision != workspace.revision:
                raise ManagerProjectionError('Editor revision changed before the draft was saved')
        except (ManagerProjectionError, ValueError) as error:
            message = _message(str(error), error=True)
            return message, message, no_update, no_update
        return None, _message('Borrador guardado en este navegador.'), document, document

    @app.callback(
        Output(ids.POSITION_PAGE, 'data'),
        Input(ids.POSITION_PREVIOUS, 'n_clicks'),
        Input(ids.POSITION_NEXT, 'n_clicks'),
        Input({'type': ids.POSITION_JUMP, 'index': ALL}, 'n_clicks'),
        Input(ids.POSITION_SIZE, 'value'),
        Input(ids.POSITION_SEARCH, 'value'),
        State(ids.POSITION_CURRENT_PAGE, 'data'),
        State({'type': ids.POSITION_JUMP, 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def change_position_page(_prev, _next, _jump, _size, _query, current, jump_ids):
        return _next_page(
            current=current,
            previous_clicks=_prev,
            next_clicks=_next,
            jump_clicks=_jump,
            jump_ids=jump_ids,
            previous_id=ids.POSITION_PREVIOUS,
            next_id=ids.POSITION_NEXT,
            jump_type=ids.POSITION_JUMP,
            reset_ids=(ids.POSITION_SIZE, ids.POSITION_SEARCH),
        )

    @app.callback(
        Output(ids.POSITION_LIST, 'children'),
        Output(ids.POSITION_STATUS, 'children'),
        Output(ids.POSITION_CURRENT_PAGE, 'data'),
        Input(ids.POSITION_PAGE, 'data'),
        Input(ids.POSITION_SEARCH, 'value'),
        Input(ids.POSITION_SIZE, 'value'),
        Input(ids.CATALOG_EDITOR, 'data'),
    )
    def refresh_positions(number, query, size, catalog_data):
        if not context.can_manage():
            return html.P('Access denied.'), '', 1
        try:
            content, page = render_position_list(
                _catalog(catalog_data),
                query,
                int(number or 1),
                int(size or 10),
            )
            return content, page_label(page), page.request.page_number
        except Exception:
            return html.P('Operational catalog could not be read.'), 'Data unavailable', 1

    @app.callback(
        Output(ids.POSITION_SELECT, 'value'),
        Output(ids.POSITION_MODAL, 'className'),
        Output(ids.POSITION_RESULT, 'children', allow_duplicate=True),
        Input({'type': ids.POSITION_EDIT, 'index': ALL}, 'n_clicks'),
        Input(ids.POSITION_NEW, 'n_clicks'),
        Input(ids.POSITION_MODAL_CANCEL, 'n_clicks'),
        Input(ids.POSITION_MODAL_CLOSE, 'n_clicks'),
        Input(ids.POSITION_MODAL_BACKDROP, 'n_clicks'),
        State({'type': ids.POSITION_EDIT, 'index': ALL}, 'id'),
        State(ids.CATALOG_EDITOR, 'data'),
        prevent_initial_call=True,
    )
    def open_position(_edits, _new, _cancel, _close, _backdrop, edit_ids, catalog_data):
        selected = ctx.triggered_id
        if (
            (selected == ids.POSITION_MODAL_CANCEL and _cancel)
            or (selected == ids.POSITION_MODAL_CLOSE and _close)
            or (selected == ids.POSITION_MODAL_BACKDROP and _backdrop)
        ):
            return no_update, modal_class(False), no_update
        if not context.can_manage():
            return no_update, no_update, no_update
        if selected == ids.POSITION_NEW and _new:
            return None, modal_class(True), None
        if isinstance(selected, dict) and selected.get('type') == ids.POSITION_EDIT:
            clicked = any(
                ident.get('index') == selected.get('index') and count
                for ident, count in zip(edit_ids or (), _edits or (), strict=True)
            )
            if not clicked:
                return no_update, no_update, no_update
            try:
                if _catalog(catalog_data).position(selected.get('index')) is not None:
                    return selected['index'], modal_class(True), None
            except (TypeError, ValueError):
                return no_update, no_update, no_update
        return no_update, no_update, no_update

    @app.callback(
        Output(ids.POSITION_ID, 'children'),
        Output(ids.POSITION_LABEL, 'value'),
        Output(ids.POSITION_ACTIVE, 'value'),
        Input(ids.POSITION_SELECT, 'value'),
        Input(ids.POSITION_MODAL, 'className'),
        State(ids.CATALOG_EDITOR, 'data'),
    )
    def select_position(position_id, _modal_state=None, catalog_data=None):
        if not context.can_manage():
            return 'Unavailable', '', []
        if not position_id:
            return 'Se generará al guardar', '', ['active']
        try:
            position = _catalog(catalog_data).position(position_id)
            if position is None:
                return 'Se generará al guardar', '', ['active']
            return position.id, position.label, ['active'] if position.active else []
        except (TypeError, ValueError):
            return 'Unavailable', '', []

    @app.callback(
        Output(ids.CATALOG_EDITOR, 'data', allow_duplicate=True),
        Output(ids.POSITION_SELECT, 'options'),
        Output(ids.POSITION_SELECT, 'value', allow_duplicate=True),
        Output(ids.POSITION_RESULT, 'children'),
        Input(ids.POSITION_APPLY, 'n_clicks'),
        State(ids.POSITION_SELECT, 'value'),
        State(ids.POSITION_LABEL, 'value'),
        State(ids.POSITION_ACTIVE, 'value'),
        State(ids.CATALOG_EDITOR, 'data'),
        prevent_initial_call=True,
    )
    def apply_position(clicks, selected, label, active, catalog_data):
        if not clicks or not context.can_manage():
            return no_update, no_update, no_update, no_update
        try:
            payload = _catalog(catalog_data).to_document()
            enabled = 'active' in (active or ())
            if selected:
                updated = context.editor.update_position(
                    payload,
                    position_id=selected,
                    label=label,
                    active=enabled,
                )
                position_id = selected
            else:
                updated, position_id = context.editor.add_position(
                    payload,
                    label=label,
                    active=enabled,
                )
            catalog = OperationalCatalog.from_document(updated)
        except Exception:
            return (
                no_update,
                no_update,
                no_update,
                _message('Position draft could not be updated.', error=True),
            )
        return (
            catalog.to_document(),
            _position_options(catalog, include_inactive=True),
            position_id,
            _message('Cargo actualizado en el editor. Guarda el borrador para conservarlo.'),
        )

    @app.callback(
        Output(ids.POSITION_MODAL, 'className', allow_duplicate=True),
        Input(ids.POSITION_RESULT, 'children'),
        prevent_initial_call=True,
    )
    def finish_position_operation(message):
        return modal_class(False) if _operation_result_kind(message) == 'success' else no_update


def _register_assignment_callbacks(
    app: object,
    context: OperationalAssignmentContext,
) -> None:
    @app.callback(
        Output(ids.ASSIGN_PAGE, 'data'),
        Input(ids.ASSIGN_PREVIOUS, 'n_clicks'),
        Input(ids.ASSIGN_NEXT, 'n_clicks'),
        Input({'type': ids.ASSIGN_JUMP, 'index': ALL}, 'n_clicks'),
        Input(ids.ASSIGN_SIZE, 'value'),
        Input(ids.ASSIGN_SEARCH, 'value'),
        State(ids.ASSIGN_CURRENT_PAGE, 'data'),
        State({'type': ids.ASSIGN_JUMP, 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def change_assignment_page(_prev, _next, _jump, _size, _query, current, jump_ids):
        return _next_page(
            current=current,
            previous_clicks=_prev,
            next_clicks=_next,
            jump_clicks=_jump,
            jump_ids=jump_ids,
            previous_id=ids.ASSIGN_PREVIOUS,
            next_id=ids.ASSIGN_NEXT,
            jump_type=ids.ASSIGN_JUMP,
            reset_ids=(ids.ASSIGN_SIZE, ids.ASSIGN_SEARCH),
        )

    @app.callback(
        Output(ids.ASSIGN_LIST, 'children'),
        Output(ids.ASSIGN_STATUS, 'children'),
        Output(ids.ASSIGN_CURRENT_PAGE, 'data'),
        Input(ids.ASSIGN_PAGE, 'data'),
        Input(ids.ASSIGN_SEARCH, 'value'),
        Input(ids.ASSIGN_SIZE, 'value'),
        Input(ids.ASSIGNMENT_RESULT, 'children'),
    )
    def refresh_assignments(number, query, size, _message):
        if not context.can_manage():
            return html.P('Access denied.'), '', 1
        try:
            content, page = render_assignment_list(
                context,
                query,
                int(number or 1),
                int(size or 10),
            )
            return content, page_label(page), page.request.page_number
        except Exception:
            return html.P('Operational assignments could not be read.'), 'Data unavailable', 1

    @app.callback(
        Output(ids.USER, 'data'),
        Output(ids.ASSIGN_SELECTED_NAME, 'children'),
        Output(ids.ASSIGN_MODAL, 'className'),
        Output(ids.ASSIGNMENT_RESULT, 'children', allow_duplicate=True),
        Output(ids.ASSIGN_FEEDBACK, 'children', allow_duplicate=True),
        Input({'type': ids.ASSIGN_EDIT, 'index': ALL}, 'n_clicks'),
        Input(ids.ASSIGN_MODAL_CANCEL, 'n_clicks'),
        Input(ids.ASSIGN_MODAL_CLOSE, 'n_clicks'),
        Input(ids.ASSIGN_MODAL_BACKDROP, 'n_clicks'),
        State({'type': ids.ASSIGN_EDIT, 'index': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def open_assignment(_edits, _cancel, _close, _backdrop, edit_ids):
        selected = ctx.triggered_id
        if (
            (selected == ids.ASSIGN_MODAL_CANCEL and _cancel)
            or (selected == ids.ASSIGN_MODAL_CLOSE and _close)
            or (selected == ids.ASSIGN_MODAL_BACKDROP and _backdrop)
        ):
            return no_update, no_update, modal_class(False), no_update, no_update
        if not isinstance(selected, dict) or selected.get('type') != ids.ASSIGN_EDIT:
            return no_update, no_update, no_update, no_update, no_update
        clicked = any(
            ident.get('index') == selected.get('index') and count
            for ident, count in zip(edit_ids or (), _edits or (), strict=True)
        )
        if not clicked or not context.can_manage():
            return no_update, no_update, no_update, no_update, no_update
        user_id = selected.get('index')
        try:
            user = next(user for user in context.promoted_users() if user.user_id == user_id)
        except StopIteration:
            return no_update, no_update, no_update, no_update, no_update
        return user_id, f'{user.display_name} · {user_id}', modal_class(True), None, None

    @app.callback(
        Output(ids.AREA, 'value'),
        Output(ids.POSITION, 'value'),
        Output(ids.GROUP, 'value'),
        Output(ids.ASSIGNMENT_REVISION, 'data'),
        Input(ids.USER, 'data'),
        Input(ids.ASSIGN_MODAL, 'className'),
    )
    def select_user(user_id, _modal_state=None):
        if not user_id or not context.can_manage():
            return None, None, None, None
        try:
            snapshot, assignment = context.service.assignment_for_edit(user_id)
            return (
                assignment.area_id,
                assignment.position_id,
                assignment.group_id,
                _revision(snapshot),
            )
        except Exception:
            return None, None, None, None

    @app.callback(
        Output(ids.POSITION, 'options', allow_duplicate=True),
        Input(ids.USER, 'data'),
        prevent_initial_call=True,
    )
    def assignment_position_options(user_id):
        if not user_id or not context.can_manage():
            return no_update
        try:
            _snapshot, assignment = context.service.assignment_for_edit(user_id)
            catalog = context.service.catalog_for_read()
            status = context.service.projection_status(CATALOG_SOURCE_KEY)
            current = (
                status.source_current_release is not None
                and status.source_current_release == status.projected_source_release
            )
            options = [
                {
                    'label': item.label,
                    'value': item.id,
                    'disabled': item.id != assignment.position_id
                    and (not item.active or not current),
                }
                for item in catalog.positions
            ]
            if assignment.position_id and all(
                item['value'] != assignment.position_id for item in options
            ):
                options.append(
                    {
                        'label': f'{assignment.position_id} (asignado, no proyectado)',
                        'value': assignment.position_id,
                        'disabled': False,
                    }
                )
            return options
        except Exception:
            return []

    @app.callback(
        Output(ids.ASSIGN_MODAL_STATUS, 'children'),
        Input(ids.USER, 'data'),
        Input(ids.ASSIGNMENT_RESULT, 'children'),
    )
    def selected_assignment_metadata(user_id, _result):
        if not user_id or not context.can_manage():
            return None
        try:
            snapshot, _value = context.service.assignment_for_edit(user_id)
            status = context.service.projection_status(assignment_source_key(user_id))
            catalog_status = context.service.projection_status(CATALOG_SOURCE_KEY)
            catalog_current = (
                catalog_status.source_current_release is not None
                and catalog_status.source_current_release == catalog_status.projected_source_release
            )
            return html.Div(
                [
                    html.Span(_status_label(status), className='ada-operational-admin__badge'),
                    html.Small(
                        'Source: '
                        f'{_release_label(
                            snapshot.current.release_ref if snapshot.current else None
                        )}'
                    ),
                    html.Small(f'Projection: {_release_label(status.projected_source_release)}'),
                    html.Small(
                        'Catálogo proyectado y vigente'
                        if catalog_current
                        else (
                            'Catálogo pendiente de proyección: no se admiten nuevas '
                            'asignaciones de cargos.'
                        )
                    ),
                ],
                className='ada-operational-admin__selected-metadata',
            )
        except Exception:
            return html.Span('Source and Projection could not be verified.')

    @app.callback(
        Output(ids.ASSIGNMENT_REVISION, 'data', allow_duplicate=True),
        Output(ids.ASSIGNMENT_RESULT, 'children'),
        Input(ids.ASSIGNMENT_SAVE, 'n_clicks'),
        State(ids.USER, 'data'),
        State(ids.AREA, 'value'),
        State(ids.POSITION, 'value'),
        State(ids.GROUP, 'value'),
        State(ids.ASSIGNMENT_REVISION, 'data'),
        prevent_initial_call=True,
    )
    def save_assignment(clicks, user_id, area, position, group, revision):
        if not clicks or not user_id or not context.can_manage():
            return no_update, no_update
        try:
            snapshot, _existing = context.service.assignment_for_edit(user_id)
            if _revision(snapshot) != revision:
                return no_update, _message(
                    'Assignment changed before it was saved. Select the user again.',
                    error=True,
                )
            assignment = OperationalAssignment(
                user_id=user_id,
                area_id=area,
                position_id=position,
                group_id=group,
            )
            context.service.publish_assignment(
                assignment,
                actor=context.principal().subject_id,
                expected=snapshot,
            )
            updated_snapshot, _value = context.service.assignment_for_edit(user_id)
        except Exception:
            return no_update, _message(
                'Assignment could not be saved. Reload and try again.',
                error=True,
            )
        try:
            context.service.project_current(assignment_source_key(user_id))
            result = _message('Asignación guardada y proyectada.')
        except Exception:
            result = _message(
                'Asignación guardada en Source. Usa Reintentar proyección.',
                warning=True,
            )
        return _revision(updated_snapshot), result

    @app.callback(
        Output(ids.ASSIGN_MODAL, 'className', allow_duplicate=True),
        Output(ids.ASSIGN_FEEDBACK, 'children'),
        Input(ids.ASSIGNMENT_RESULT, 'children'),
        prevent_initial_call=True,
    )
    def finish_assignment_operation(message):
        kind = _operation_result_kind(message)
        if kind not in {'success', 'warning'}:
            return no_update, no_update
        return modal_class(False), message if kind == 'warning' else None

    @app.callback(
        Output(ids.ASSIGNMENT_RESULT, 'children', allow_duplicate=True),
        Input(ids.ASSIGNMENT_REPROJECT, 'n_clicks'),
        State(ids.USER, 'data'),
        prevent_initial_call=True,
    )
    def reproject_assignment(clicks, user_id):
        if not clicks or not user_id or not context.can_manage():
            return no_update
        try:
            result = context.service.project_current(assignment_source_key(user_id))
            return _message(
                'Asignación proyectada.' if result is not None else 'No hay publicación.'
            )
        except Exception:
            return _message('Assignment could not be projected.', error=True)


def _catalog(document: dict[str, object] | None) -> OperationalCatalog:
    if not isinstance(document, dict):
        raise ValueError('Operational catalog editor data is invalid')
    return OperationalCatalog.from_document(document)


def _operation_result_kind(message: object) -> str | None:
    if isinstance(message, dict):
        style = (message.get('props') or {}).get('className', '')
    else:
        style = getattr(message, 'className', '')
    if not isinstance(style, str):
        return None
    tokens = set(style.split())
    for kind in ('success', 'warning', 'error'):
        if f'ada-operational-admin__result--{kind}' in tokens:
            return kind
    return None


def _next_page(
    *,
    current: int | None,
    previous_clicks: int | None,
    next_clicks: int | None,
    jump_clicks: list[int | None] | None,
    jump_ids: list[dict[str, object]] | None,
    previous_id: str,
    next_id: str,
    jump_type: str,
    reset_ids: tuple[str, str],
) -> object:
    trigger = ctx.triggered_id
    if trigger in reset_ids:
        return 1
    if isinstance(trigger, dict) and trigger.get('type') == jump_type:
        clicked = any(
            ident.get('index') == trigger.get('index') and count
            for ident, count in zip(jump_ids or (), jump_clicks or (), strict=True)
        )
        return int(trigger['index']) if clicked else no_update
    if trigger == previous_id and previous_clicks:
        return max(1, int(current or 1) - 1)
    if trigger == next_id and next_clicks:
        return int(current or 1) + 1
    return no_update


def _message(value: str, *, error: bool = False, warning: bool = False) -> object:
    state = 'error' if error else 'warning' if warning else 'success'
    return html.P(
        value,
        className=f'ada-operational-admin__result ada-operational-admin__result--{state}',
    )


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0
