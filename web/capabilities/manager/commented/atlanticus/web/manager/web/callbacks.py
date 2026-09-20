# Espejo pedagógico: mantiene el mismo AST que producción y documenta el contrato Manager en español.
from __future__ import annotations

from datetime import datetime

from dash import ALL, MATCH, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import (
    ManagerError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.models import ManagerModule, ManagerSurfaceDefinition
from atlanticus.web.manager.projection import (
    ProjectionIssue,
    ProjectionState,
    resolve_projection_state,
)
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.home import build_home_page_content, build_manager_home_return
from atlanticus.web.manager.web.ids import (
    CONTENT_ID,
    HOME_CARDS_ID,
    HOME_ID,
    HOME_NEXT_ID,
    HOME_PAGE_LABEL_ID,
    HOME_PAGE_STORE_ID,
    HOME_PREVIOUS_ID,
    LOCATION_ID,
    REFRESH_SIGNAL_ID,
    SIDEBAR_BACKDROP_ID,
    SIDEBAR_CLOSE_ID,
    SIDEBAR_ID,
    SIDEBAR_MODULES_ID,
    SIDEBAR_TOGGLE_ID,
    STATUS_STORE_ID,
    SUMMARY_ID,
    history_preview_open_id,
    module_section_button_id,
    module_section_panel_id,
    module_section_store_id,
    module_status_id,
    workflow_action_id,
    workflow_conflict_details_id,
    workflow_conflict_id,
    workflow_draft_id,
    workflow_draft_status_id,
    workflow_editor_revision_id,
    workflow_history_id,
    workflow_history_preview_body_id,
    workflow_history_preview_close_id,
    workflow_history_preview_heading_id,
    workflow_history_preview_id,
    workflow_history_preview_load_id,
    workflow_history_preview_meta_id,
    workflow_history_preview_store_id,
    workflow_projection_signal_id,
    workflow_refresh_signal_id,
    workflow_result_id,
    workflow_saved_draft_id,
    workflow_saved_draft_status_id,
    workflow_source_verification_id,
    workflow_status_id,
    workflow_validation_id,
    workflow_workspace_command_id,
    workflow_workspace_confirmation_id,
    workflow_workspace_confirmation_message_id,
    workflow_workspace_confirmation_title_id,
    workflow_workspace_reset_signal_id,
)
from atlanticus.web.manager.web.layout import (
    build_entry_content,
    build_module_content,
    build_sidebar_modules,
    build_summary,
    build_workflow_history_content,
    build_workflow_status_content,
)
from atlanticus.web.manager.web.workspace import (
    build_saved_workspace_content,
    build_source_conflict_content,
    build_workspace_content,
)
from atlanticus.web.manager.workspace import ManagerWorkspaceController
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceReleaseId, SourceReleaseRef


def register_manager_callbacks(
    app: object,
    *,
    definition: ManagerSurfaceDefinition,
    registry: ManagerModuleRegistry,
    services: ServiceRegistry,
    authorization: ManagerAuthorizationPolicy,
) -> None:
    coordinator = ManagerProjectionCoordinator(
        registry=registry, services=services, authorization=authorization
    )
    workspace_controller = ManagerWorkspaceController(coordinator)
    source_inputs = [
        Input(module.source_signal_id, 'data')
        for module in registry.modules
        if module.source_signal_id is not None
    ]

    @app.callback(
        Output(SIDEBAR_ID, 'className'),
        Output(SIDEBAR_BACKDROP_ID, 'className'),
        Input(SIDEBAR_TOGGLE_ID, 'n_clicks'),
        Input(SIDEBAR_CLOSE_ID, 'n_clicks'),
        Input(SIDEBAR_BACKDROP_ID, 'n_clicks'),
        Input(LOCATION_ID, 'pathname'),
        prevent_initial_call=True,
    )
    def toggle_sidebar(_open: int, _close: int, _backdrop: int, _pathname: str):
        if ctx.triggered_id == SIDEBAR_TOGGLE_ID:
            return (
                'atlanticus-manager__sidebar atlanticus-manager__sidebar--open',
                'atlanticus-manager__sidebar-backdrop atlanticus-manager__sidebar-backdrop--open',
            )
        return 'atlanticus-manager__sidebar', 'atlanticus-manager__sidebar-backdrop'

    @app.callback(
        Output(STATUS_STORE_ID, 'data'),
        Output(SUMMARY_ID, 'children'),
        Input(REFRESH_SIGNAL_ID, 'data'),
        Input(workflow_refresh_signal_id(ALL), 'data'),
        *source_inputs,
    )
    def refresh_statuses(_refresh: int, _workflow_signals: list[object], *_signals: object):
        principal = definition.principal_provider()
        states = {}
        for module in registry.visible_modules(principal, authorization):
            try:
                state = resolve_projection_state(coordinator.get_status(module.key, principal))
            except Exception:
                state = ProjectionState.UNAVAILABLE
            states[module.key] = state.value
        return states, build_summary({key: ProjectionState(value) for key, value in states.items()})

    @app.callback(
        Output(SUMMARY_ID, 'hidden'),
        Output(HOME_ID, 'hidden'),
        Output(CONTENT_ID, 'hidden'),
        Input(LOCATION_ID, 'pathname'),
    )
    def render_surface_visibility(pathname: str | None):
        home_active = (pathname or registry.root_route) == registry.root_route
        return not home_active, not home_active, home_active

    @app.callback(
        Output(workflow_validation_id(ALL), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(ALL), 'data', allow_duplicate=True),
        Input(REFRESH_SIGNAL_ID, 'data'),
        prevent_initial_call=True,
    )
    def clear_transient_workflow(clicks: int):
        if not _click_is_real(clicks):
            return no_update, no_update
        principal = definition.principal_provider()
        cleared = [None for _ in registry.visible_modules(principal, authorization)]
        return cleared, cleared

    @app.callback(
        Output(SIDEBAR_MODULES_ID, 'children'),
        Input(STATUS_STORE_ID, 'data'),
        Input(LOCATION_ID, 'pathname'),
    )
    def render_sidebar(states_data: dict[str, str] | None, pathname: str | None):
        principal = definition.principal_provider()
        states = {key: _safe_state(value) for key, value in (states_data or {}).items()}
        return build_sidebar_modules(
            registry=registry,
            modules=registry.visible_items(principal, authorization),
            current_path=pathname or registry.root_route,
            states=states,
        )

    @app.callback(
        Output(HOME_CARDS_ID, 'children'),
        Output(HOME_PAGE_LABEL_ID, 'children'),
        Output(HOME_PREVIOUS_ID, 'disabled'),
        Output(HOME_NEXT_ID, 'disabled'),
        Output(HOME_PAGE_STORE_ID, 'data'),
        Input(HOME_PREVIOUS_ID, 'n_clicks'),
        Input(HOME_NEXT_ID, 'n_clicks'),
        Input(STATUS_STORE_ID, 'data'),
        State(HOME_PAGE_STORE_ID, 'data'),
    )
    def render_home_page(previous_clicks, next_clicks, states_data, current_page):
        page = current_page if isinstance(current_page, int) else 1
        if ctx.triggered_id == HOME_PREVIOUS_ID and _click_is_real(previous_clicks):
            page -= 1
        elif ctx.triggered_id == HOME_NEXT_ID and _click_is_real(next_clicks):
            page += 1
        principal = definition.principal_provider()
        states = {key: _safe_state(value) for key, value in (states_data or {}).items()}
        return build_home_page_content(
            registry=registry,
            modules=registry.visible_items(principal, authorization),
            states=states,
            page=page,
        )

    @app.callback(Output(CONTENT_ID, 'children'), Input(LOCATION_ID, 'pathname'))
    def render_content(pathname: str | None):
        current_path = pathname or registry.root_route
        if current_path == registry.root_route:
            return None
        principal = definition.principal_provider()
        item = registry.find_by_route(current_path)
        if item is None or not authorization.can_view(principal, item):
            return _error_message('Manager entry was not found')
        content = (
            build_module_content(
                module=item,
                services=services,
                coordinator=coordinator,
                principal=principal,
            )
            if isinstance(item, ManagerModule)
            else build_entry_content(entry=item, services=services)
        )
        return html.Div(
            [build_manager_home_return(registry.root_route), content],
            className='atlanticus-manager__module-page',
        )

    @app.callback(
        Output(module_section_panel_id(MATCH, 'content'), 'children'),
        Input(workflow_workspace_reset_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def reset_editor_surface(_reset_signal: int | None):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update
        module_key = str(trigger.get('module', ''))
        try:
            module = registry.require(module_key)
        except ManagerError:
            return no_update
        principal = definition.principal_provider()
        if not authorization.can_view(principal, module):
            return no_update
        return module.layout(services)

    @app.callback(
        Output(module_section_store_id(MATCH), 'data'),
        Input(module_section_button_id(MATCH, ALL), 'n_clicks'),
        State(module_section_button_id(MATCH, ALL), 'id'),
        State(module_section_store_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def select_section(clicks, button_ids, current):
        trigger = ctx.triggered_id
        if not _pattern_click_is_real(trigger, clicks, button_ids):
            return current
        return str(trigger.get('section', current))

    @app.callback(
        Output(module_section_panel_id(MATCH, 'content'), 'className'),
        Output(module_section_panel_id(MATCH, 'workflow'), 'className'),
        Output(module_section_button_id(MATCH, 'content'), 'className'),
        Output(module_section_button_id(MATCH, 'workflow'), 'className'),
        Input(module_section_store_id(MATCH), 'data'),
    )
    def render_section(section: str):
        content_active = section == 'content'
        workflow_active = section == 'workflow'
        return (
            _panel_class(content_active),
            _panel_class(workflow_active),
            _tab_class(content_active),
            _tab_class(workflow_active),
        )

    @app.callback(
        Output(workflow_status_id(ALL), 'children'),
        Output(workflow_history_id(ALL), 'children'),
        Output(workflow_action_id(ALL, 'project'), 'disabled'),
        Output(module_status_id(ALL), 'children'),
        Output(module_status_id(ALL), 'className'),
        Input(STATUS_STORE_ID, 'data'),
        Input(LOCATION_ID, 'pathname'),
        Input(workflow_refresh_signal_id(ALL), 'data'),
    )
    def refresh_active_workflow(_status_data, pathname, _signals):
        principal = definition.principal_provider()
        item = registry.find_by_route(pathname or '')
        if not isinstance(item, ManagerModule) or not authorization.can_view(principal, item):
            raise PreventUpdate
        module = item
        try:
            status = coordinator.get_status(module.key, principal)
            history = (
                coordinator.list_history(module.key, principal, limit=20)
                if coordinator.can_load_history(module.key, principal)
                else None
            )
            target = coordinator.get_current_projection_target(module.key, principal)
            error = None
            state = resolve_projection_state(status)
        except Exception:
            status = None
            history = None
            target = None
            error = 'Configuration status could not be loaded'
            state = ProjectionState.UNAVAILABLE
        return (
            [build_workflow_status_content(module=module, status=status, error=error)],
            [
                build_workflow_history_content(
                    module=module, status=status, history=history, error=error
                )
            ],
            [target is None],
            [_state_label(state)],
            [_state_class(state)],
        )

    @app.callback(
        Output(workflow_draft_status_id(MATCH), 'children'),
        Output(workflow_action_id(MATCH, 'save-draft'), 'disabled'),
        Output(workflow_action_id(MATCH, 'validate'), 'disabled'),
        Output(workflow_action_id(MATCH, 'verify-source'), 'disabled'),
        Output(workflow_action_id(MATCH, 'publish'), 'disabled'),
        Output(workflow_action_id(MATCH, 'discard-local'), 'disabled'),
        Output(workflow_conflict_id(MATCH), 'hidden'),
        Output(workflow_conflict_details_id(MATCH), 'children'),
        Input(workflow_draft_id(MATCH), 'data'),
        Input(workflow_validation_id(MATCH), 'data'),
        Input(workflow_source_verification_id(MATCH), 'data'),
        Input(workflow_editor_revision_id(MATCH), 'data'),
        # El store de sección sólo existe para el módulo montado. Su MATCH impide que
        # stores globales creen una instancia de este callback para módulos fuera del DOM.
        Input(module_section_store_id(MATCH), 'data'),
        State(workflow_draft_id(MATCH), 'id'),
    )
    def refresh_workspace(
        draft_data,
        validation_data,
        verification_data,
        editor_revision,
        _section,
        draft_id,
    ):
        principal = definition.principal_provider()
        module_key = str(draft_id.get('module', ''))
        try:
            state = workspace_controller.load_state(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
                validation_document=validation_data,
                verification_document=verification_data,
                editor_revision=editor_revision,
            )
            if isinstance(draft_data, dict) and state.workspace is None:
                raise ManagerProjectionError('Browser workspace is invalid')
        except ManagerError as error:
            return _error_message(str(error)), True, True, True, True, True, True, None
        conflict = None
        if (
            state.lifecycle.source_conflict
            and state.workspace is not None
            and state.verification is not None
        ):
            conflict = build_source_conflict_content(
                workspace=state.workspace, verification=state.verification
            )
        return (
            build_workspace_content(
                workspace=state.workspace,
                source=state.source,
                validation=None if state.lifecycle.dirty else validation_data,
                verification=None if state.lifecycle.dirty else state.verification,
                lifecycle=state.lifecycle,
                principal=principal,
            ),
            not state.lifecycle.can_save_draft,
            not state.lifecycle.can_validate,
            not state.lifecycle.can_verify_source,
            not state.lifecycle.can_publish,
            not state.lifecycle.can_discard_local,
            not state.lifecycle.source_conflict,
            conflict,
        )

    @app.callback(
        Output(workflow_saved_draft_status_id(MATCH), 'children'),
        Output(workflow_action_id(MATCH, 'recover-saved-draft'), 'disabled'),
        Output(workflow_action_id(MATCH, 'discard-saved-draft'), 'disabled'),
        Input(workflow_saved_draft_id(MATCH), 'data'),
        # Esta entrada page-local limita el MATCH al módulo que está realmente montado.
        Input(module_section_store_id(MATCH), 'data'),
        State(workflow_saved_draft_id(MATCH), 'id'),
    )
    def refresh_saved_workspace(saved_data, _section, saved_id):
        principal = definition.principal_provider()
        module_key = str(saved_id.get('module', ''))
        if saved_data is None:
            return build_saved_workspace_content(workspace=None, source=None), True, True
        workspace = workspace_controller.safe_workspace(saved_data, principal)
        if workspace is None:
            return (
                build_saved_workspace_content(workspace=None, source=None, incompatible=True),
                True,
                False,
            )
        try:
            source = coordinator.load_current_source(module_key, principal)
        except Exception:
            source = None
        return build_saved_workspace_content(workspace=workspace, source=source), False, False

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_saved_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_editor_revision_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'recover-saved-draft'), 'n_clicks'),
        Input(workflow_action_id(MATCH, 'discard-saved-draft'), 'n_clicks'),
        State(workflow_saved_draft_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def manage_saved_browser_draft(recover_clicks, discard_clicks, saved_data):
        trigger = ctx.triggered_id
        action = trigger.get('action') if isinstance(trigger, dict) else None
        clicks = recover_clicks if action == 'recover-saved-draft' else discard_clicks
        if action not in {'recover-saved-draft', 'discard-saved-draft'} or not _click_is_real(
            clicks
        ):
            return (no_update,) * 6
        if action == 'discard-saved-draft':
            return (
                _notice_message('El borrador guardado fue descartado de este navegador.'),
                no_update,
                None,
                no_update,
                no_update,
                no_update,
            )
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', ''))
        try:
            workspace = workspace_controller.require_workspace(saved_data, principal)
            source = coordinator.load_current_source(module_key, principal)
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update, no_update
        source_changed = workspace_controller.source_changed(workspace, source)
        message = (
            'Workspace recuperado. Source cambió desde que se guardó; revisa el contenido y verifica Source antes de publicar.'
            if source_changed
            else 'Workspace recuperado en el navegador.'
        )
        return _notice_message(message), saved_data, no_update, None, None, workspace.revision

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'validate'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def validate_configuration(clicks, draft_data, editor_revision):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        try:
            result = workspace_controller.validate(
                module_key=str(trigger.get('module', '')),
                principal=definition.principal_provider(),
                workspace_document=draft_data,
                editor_revision=editor_revision,
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update
        except Exception:
            return _error_message('Validation could not be completed'), no_update, no_update
        validation = {
            'draft_revision': result.draft_revision,
            'valid': result.valid,
            'validated_by': result.audit.actor,
            'validated_at': result.audit.occurred_at.isoformat(),
            'issues': [_issue_document(issue) for issue in result.issues],
        }
        return None, validation, None

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'verify-source'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_validation_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def verify_source_configuration(
        clicks, draft_data, validation_data, editor_revision, refresh_signal
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        try:
            result = workspace_controller.verify(
                module_key=str(trigger.get('module', '')),
                principal=definition.principal_provider(),
                workspace_document=draft_data,
                validation_document=validation_data,
                editor_revision=editor_revision,
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update
        except Exception:
            return (
                _error_message('Source verification could not be completed'),
                no_update,
                no_update,
            )
        return None, result.to_document(), int(refresh_signal or 0) + 1

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_saved_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'publish'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_validation_id(MATCH), 'data'),
        State(workflow_source_verification_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def publish_configuration(
        clicks, draft_data, validation_data, verification_data, editor_revision, refresh_signal
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return (no_update,) * 5
        module_key = str(trigger.get('module', ''))
        principal = definition.principal_provider()
        try:
            _result, updated = workspace_controller.publish(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
                validation_document=validation_data,
                verification_document=verification_data,
                editor_revision=editor_revision,
            )
        except ManagerSourceConflictError:
            refreshed = workspace_controller.refresh_verification(
                module_key=module_key, principal=principal, workspace_document=draft_data
            )
            return (
                _notice_message(
                    'La fuente cambió antes de completar la publicación. Revisa el detalle antes de continuar.'
                ),
                int(refresh_signal or 0) + 1,
                no_update,
                no_update,
                refreshed,
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update
        except Exception:
            return (
                _error_message('Configuration could not be published'),
                no_update,
                no_update,
                no_update,
                no_update,
            )
        return None, int(refresh_signal or 0) + 1, updated, None, None

    @app.callback(
        Output(workflow_draft_id(MATCH), 'data'),
        Output(workflow_validation_id(MATCH), 'data'),
        Output(workflow_source_verification_id(MATCH), 'data'),
        Input(workflow_refresh_signal_id(MATCH), 'data'),
        Input(LOCATION_ID, 'pathname'),
        State(workflow_refresh_signal_id(MATCH), 'id'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
    )
    def hydrate_source_workspace(
        _refresh_signal, pathname, refresh_id, draft_data, editor_revision
    ):
        # Los stores del workspace existen para todos los módulos para conservar el estado
        # al navegar, pero la hidratación debe ejecutarse únicamente para la ruta activa.
        module_key = str(refresh_id.get('module', ''))
        active_item = registry.find_by_route(pathname or '')
        if not isinstance(active_item, ManagerModule) or active_item.key != module_key:
            raise PreventUpdate
        principal = definition.principal_provider()
        try:
            if workspace_controller.has_local_work(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
                editor_revision=editor_revision,
            ):
                return no_update, no_update, no_update
            updated = workspace_controller.replace_from_source(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
            )
        except Exception:
            return no_update, no_update, no_update
        if updated is None:
            return None, None, None
        return updated, None, None

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'update-source'), 'n_clicks'),
        Input(workflow_action_id(MATCH, 'keep-draft'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_source_verification_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def update_from_source(
        update_clicks, keep_clicks, draft_data, verification_data, refresh_signal
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return (no_update,) * 5
        action = str(trigger.get('action', ''))
        clicks = update_clicks if action == 'update-source' else keep_clicks
        if action not in {'update-source', 'keep-draft'} or not _click_is_real(clicks):
            return (no_update,) * 5
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', ''))
        try:
            if action == 'keep-draft':
                updated = workspace_controller.keep_draft(
                    principal=principal,
                    workspace_document=draft_data,
                    verification_document=verification_data,
                )
                return (
                    _notice_message(
                        'Tu workspace se conservó. Vuelve a verificar Source antes de publicar.'
                    ),
                    updated,
                    no_update,
                    None,
                    no_update,
                )
            updated = workspace_controller.replace_from_source(
                module_key=module_key, principal=principal, workspace_document=draft_data
            )
            return None, updated, None, None, int(refresh_signal or 0) + 1
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update
        except Exception:
            return (
                _error_message('Current source could not be loaded'),
                no_update,
                no_update,
                no_update,
                no_update,
            )

    @app.callback(
        Output(workflow_workspace_confirmation_id(MATCH), 'hidden'),
        Output(workflow_workspace_confirmation_title_id(MATCH), 'children'),
        Output(workflow_workspace_confirmation_message_id(MATCH), 'children'),
        Output(workflow_workspace_command_id(MATCH), 'data'),
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_editor_revision_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_workspace_reset_signal_id(MATCH), 'data'),
        Input(workflow_action_id(MATCH, 'discard-local'), 'n_clicks'),
        Input(workflow_action_id(MATCH, 'reload'), 'n_clicks'),
        Input(workflow_action_id(MATCH, 'workspace-confirm'), 'n_clicks'),
        Input(workflow_action_id(MATCH, 'workspace-cancel'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        State(workflow_workspace_command_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        State(workflow_workspace_reset_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def manage_local_workspace(
        discard_clicks,
        reload_clicks,
        confirm_clicks,
        cancel_clicks,
        draft_data,
        editor_revision,
        command,
        refresh_signal,
        reset_signal,
    ):
        trigger = ctx.triggered_id
        action = trigger.get('action') if isinstance(trigger, dict) else None
        clicks = {
            'discard-local': discard_clicks,
            'reload': reload_clicks,
            'workspace-confirm': confirm_clicks,
            'workspace-cancel': cancel_clicks,
        }.get(str(action))
        if not _click_is_real(clicks):
            return (no_update,) * 11
        if action == 'workspace-cancel':
            return (
                True,
                None,
                None,
                None,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', '')) if isinstance(trigger, dict) else ''
        try:
            module = registry.require(module_key)
            has_local_work = workspace_controller.has_local_work(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
                editor_revision=editor_revision,
            )
        except ManagerError as error:
            return (
                True,
                None,
                None,
                None,
                _error_message(str(error)),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        if action == 'discard-local':
            if not has_local_work:
                return (
                    True,
                    None,
                    None,
                    None,
                    _notice_message('No hay cambios locales para descartar.'),
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )
            return (
                False,
                'Descartar cambios locales',
                f'Se descartarán los cambios locales y se restaurará la versión actual de {module.source_name}. La fuente de verdad y la proyección runtime no se modificarán.',
                'discard',
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        if action == 'reload' and has_local_work:
            return (
                False,
                'Descartar cambios y recargar',
                f'Se descartarán los cambios locales, se restaurará la versión actual de {module.source_name} y se volverán a consultar la fuente, el historial y la proyección. No se publicará ni proyectará nada.',
                'reload',
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        resolved_command = command if action == 'workspace-confirm' else 'reload'
        if resolved_command not in {'discard', 'reload'}:
            return (no_update,) * 11
        try:
            source_document = workspace_controller.replace_from_source(
                module_key=module_key,
                principal=principal,
                workspace_document=draft_data,
            )
            source_workspace = (
                workspace_controller.require_workspace(source_document, principal)
                if source_document is not None
                else None
            )
        except ManagerSourceConflictError:
            return (
                True,
                None,
                None,
                None,
                _notice_message(
                    f'{module.source_name} cambió mientras se restauraba el workspace. Vuelve a intentarlo.'
                ),
                no_update,
                no_update,
                no_update,
                no_update,
                int(refresh_signal or 0) + 1,
                no_update,
            )
        except ManagerError as error:
            return (
                True,
                None,
                None,
                None,
                _error_message(str(error)),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        except Exception:
            return (
                True,
                None,
                None,
                None,
                _error_message('Current source could not be restored'),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        next_refresh = int(refresh_signal or 0) + 1
        if source_workspace is None:
            message = f'{module.source_name} no tiene una configuración publicada. El workspace local quedó vacío.'
            draft_output = None
            editor_output = None
            reset_output = int(reset_signal or 0) + 1
        else:
            message = (
                f'Workspace restaurado desde la versión actual de {module.source_name}.'
                if resolved_command == 'discard'
                else f'Estado remoto recargado y workspace actualizado desde {module.source_name}.'
            )
            draft_output = source_document
            editor_output = source_workspace.revision
            reset_output = no_update
        return (
            True,
            None,
            None,
            None,
            _notice_message(message),
            draft_output,
            None,
            None,
            editor_output,
            next_refresh,
            reset_output,
        )

    @app.callback(
        Output(workflow_history_preview_id(MATCH), 'hidden'),
        Output(workflow_history_preview_heading_id(MATCH), 'children'),
        Output(workflow_history_preview_meta_id(MATCH), 'children'),
        Output(workflow_history_preview_body_id(MATCH), 'children'),
        Output(workflow_history_preview_store_id(MATCH), 'data'),
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Input(history_preview_open_id(MATCH, ALL, ALL, ALL, current=ALL, active=ALL), 'n_clicks'),
        Input(workflow_history_preview_close_id(MATCH), 'n_clicks'),
        State(history_preview_open_id(MATCH, ALL, ALL, ALL, current=ALL, active=ALL), 'id'),
        prevent_initial_call=True,
    )
    def manage_history_preview(clicks, close_clicks, preview_ids):
        trigger = ctx.triggered_id
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-manager-history-preview-close'
        ):
            return (
                (True, None, None, None, None, no_update)
                if _click_is_real(close_clicks)
                else (no_update,) * 6
            )
        if not _pattern_click_is_real(trigger, clicks, preview_ids):
            return (no_update,) * 6
        module_key = str(trigger.get('module', ''))
        try:
            module = registry.require(module_key)
            if module.history_preview_renderer is None:
                raise ManagerProjectionError('Manager module does not support history preview')
            release_ref = SourceReleaseRef(
                release_id=SourceReleaseId(str(trigger.get('release_id', ''))),
                published_at_utc=datetime.fromisoformat(str(trigger.get('published_at_utc', ''))),
            )
            history_result = coordinator.load_history_release(
                module_key, definition.principal_provider(), release_ref
            )
            preview = module.history_preview_renderer(history_result.payload)
        except ManagerError as error:
            return True, None, None, None, None, _error_message(str(error))
        except Exception:
            return (
                True,
                None,
                None,
                None,
                None,
                _error_message('History release preview could not be loaded'),
            )
        release_id = history_result.release_ref.release_id.value
        state = {
            'schema_version': 2,
            'module_key': module_key,
            'source_release': {
                'release_id': release_id,
                'published_at_utc': history_result.release_ref.published_at_utc.isoformat(),
            },
            'payload': history_result.payload,
        }
        return False, f'Release {release_id[:12]}', None, preview, state, None

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_history_preview_id(MATCH), 'hidden', allow_duplicate=True),
        Output(workflow_history_preview_store_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_history_preview_load_id(MATCH), 'n_clicks'),
        State(workflow_history_preview_store_id(MATCH), 'data'),
        State(workflow_draft_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def load_history_preview_as_draft(clicks, preview_data, workspace_data):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return (no_update,) * 6
        module_key = str(trigger.get('module', ''))
        try:
            payload = _history_preview_payload(preview_data, module_key)
            principal = definition.principal_provider()
            updated = (
                workspace_controller.replace_with_payload(
                    principal=principal, workspace_document=workspace_data, payload=payload
                )
                if isinstance(workspace_data, dict)
                else workspace_controller.create_with_payload_on_current_base(
                    module_key=module_key, principal=principal, payload=payload
                )
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update, no_update
        return (
            _notice_message(
                'Release histórica cargada como cambios locales. Valida y verifica Source antes de publicar.'
            ),
            updated,
            None,
            None,
            True,
            None,
        )

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_projection_signal_id(MATCH), 'data'),
        Input(workflow_action_id(MATCH, 'project'), 'n_clicks'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def project_configuration(clicks, refresh_signal):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        module_key = str(trigger.get('module', ''))
        try:
            principal = definition.principal_provider()
            target = coordinator.get_current_projection_target(module_key, principal)
            if target is None:
                raise ManagerProjectionError('A published source target is required')
            result = coordinator.project(module_key, principal, target)
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update
        except Exception:
            return _error_message('Configuration could not be projected'), no_update, no_update
        signal = {
            'source_key': result.target.source_key.value,
            'source_release_id': result.target.source_release_id.value,
            'source_published_at_utc': result.target.source_release.published_at_utc.isoformat(),
            'projected_at_utc': result.projection.projected_at_utc.isoformat(),
        }
        return None, int(refresh_signal or 0) + 1, signal


def _history_preview_payload(data: dict[str, object] | None, module_key: str) -> dict[str, object]:
    if (
        not isinstance(data, dict)
        or data.get('schema_version') != 2
        or str(data.get('module_key', '')) != module_key
    ):
        raise ManagerProjectionError('History preview is not available')
    payload = data.get('payload')
    if not isinstance(payload, dict):
        raise ManagerProjectionError('History preview payload is invalid')
    return dict(payload)


def _issue_document(issue: ProjectionIssue) -> dict[str, object]:
    return {'code': issue.code, 'message': issue.message, 'level': issue.level, 'path': issue.path}


def _notice_message(message: str):
    return html.Div(
        message, className='atlanticus-manager__message atlanticus-manager__message--notice'
    )


def _error_message(message: str):
    return html.Div(
        message, className='atlanticus-manager__message atlanticus-manager__message--error'
    )


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0


def _pattern_click_is_real(trigger, clicks, ids) -> bool:
    if not isinstance(trigger, dict):
        return False
    return any(
        dict(item_id) == dict(trigger) and _click_is_real(click_count)
        for item_id, click_count in zip(ids or [], clicks or [], strict=False)
    )


def _safe_state(value: str) -> ProjectionState:
    try:
        return ProjectionState(value)
    except ValueError:
        return ProjectionState.UNAVAILABLE


def _state_label(state: ProjectionState) -> str:
    return {
        ProjectionState.NO_SOURCE: 'Sin fuente',
        ProjectionState.SYNCHRONIZED: 'Actualizada',
        ProjectionState.READY: 'Lista',
        ProjectionState.UNAVAILABLE: 'No disponible',
    }[state]


def _state_class(state: ProjectionState) -> str:
    return f'atlanticus-manager__state atlanticus-manager__state--{state.value}'


def _panel_class(active: bool) -> str:
    base = 'atlanticus-manager__section-panel'
    return f'{base} {base}--active' if active else base


def _tab_class(active: bool) -> str:
    base = 'atlanticus-manager__tab'
    return f'{base} {base}--active' if active else base
