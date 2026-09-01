from __future__ import annotations

from dash import ALL, MATCH, Input, Output, State, ctx, html, no_update

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import (
    ManagerError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.lifecycle import resolve_manager_lifecycle
from atlanticus.web.manager.models import ManagerPrincipal, ManagerSurfaceDefinition
from atlanticus.web.manager.projection import (
    ManagerDraft,
    ProjectionIssue,
    ProjectionState,
    ProjectionStatus,
    SourceVerificationResult,
    resolve_projection_state,
)
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.ids import (
    CONTENT_ID,
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
    workflow_revision_id,
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
    build_module_content,
    build_saved_draft_content,
    build_sidebar_modules,
    build_source_conflict_content,
    build_summary,
    build_workflow_draft_content,
    build_workflow_history_content,
    build_workflow_status_content,
)
from atlanticus.web.services import ServiceRegistry


def register_manager_callbacks(
    app: object,
    *,
    definition: ManagerSurfaceDefinition,
    registry: ManagerModuleRegistry,
    services: ServiceRegistry,
    authorization: ManagerAuthorizationPolicy,
) -> None:
    coordinator = ManagerProjectionCoordinator(
        registry=registry,
        services=services,
        authorization=authorization,
    )
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
        trigger = ctx.triggered_id
        if trigger == SIDEBAR_TOGGLE_ID:
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
    def refresh_statuses(_refresh_clicks: int, _workflow_signals: list[object], *_signals: object):
        principal = definition.principal_provider()
        states: dict[str, str] = {}
        for module in registry.visible_modules(principal, authorization):
            try:
                state = resolve_projection_state(coordinator.get_status(module.key, principal))
            except Exception:
                state = ProjectionState.UNAVAILABLE
            states[module.key] = state.value
        resolved_states = {key: ProjectionState(value) for key, value in states.items()}
        return states, build_summary(resolved_states)

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
        visible_modules = registry.visible_modules(principal, authorization)
        cleared = [None for _ in visible_modules]
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
            modules=registry.visible_modules(principal, authorization),
            current_path=(
                pathname or registry.route_for(registry.require(definition.default_module_key))
            ),
            states=states,
        )

    @app.callback(
        Output(CONTENT_ID, 'children'),
        Input(LOCATION_ID, 'pathname'),
    )
    def render_content(pathname: str | None):
        principal = definition.principal_provider()
        module = _active_module(registry, definition, pathname)
        if module is None or not authorization.can_view(principal, module):
            from dash import html

            return html.Div(
                'Configuration module was not found',
                className='atlanticus-manager__message atlanticus-manager__message--error',
            )
        return build_module_content(
            module=module,
            services=services,
            coordinator=coordinator,
            principal=principal,
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
    def select_section(
        clicks: list[int],
        button_ids: list[dict[str, object]],
        current: str,
    ):
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
        Output(workflow_revision_id(ALL), 'data'),
        Output(workflow_action_id(ALL, 'project'), 'disabled'),
        Output(module_status_id(ALL), 'children'),
        Output(module_status_id(ALL), 'className'),
        Input(STATUS_STORE_ID, 'data'),
        Input(LOCATION_ID, 'pathname'),
        Input(workflow_refresh_signal_id(ALL), 'data'),
    )
    def refresh_active_workflow(
        _status_data: dict[str, str] | None,
        pathname: str | None,
        _workflow_signals: list[object],
    ):
        principal = definition.principal_provider()
        module = _active_module(registry, definition, pathname)
        if module is None or not authorization.can_view(principal, module):
            return [], [], [], [], [], []
        status, history, can_load_history, status_error = _load_workflow_state(
            coordinator,
            module.key,
            principal,
        )
        state = (
            resolve_projection_state(status) if status is not None else ProjectionState.UNAVAILABLE
        )
        return (
            [
                build_workflow_status_content(
                    module=module,
                    status=status,
                    error=status_error,
                )
            ],
            [
                build_workflow_history_content(
                    module=module,
                    status=status,
                    history=history,
                    can_load_history=can_load_history,
                    error=status_error,
                )
            ],
            [_workflow_revision_state(status)],
            [not _can_project(status)],
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
        Output(workflow_action_id(MATCH, 'force-publish'), 'disabled'),
        Input(workflow_draft_id(MATCH), 'data'),
        Input(workflow_validation_id(MATCH), 'data'),
        Input(workflow_source_verification_id(MATCH), 'data'),
        Input(workflow_revision_id(MATCH), 'data'),
        Input(workflow_editor_revision_id(MATCH), 'data'),
    )
    def refresh_draft_workflow(
        draft_data: dict[str, object] | None,
        validation_data: dict[str, object] | None,
        verification_data: dict[str, object] | None,
        revision_state: dict[str, object] | None,
        editor_revision: str | None,
    ):
        principal = definition.principal_provider()
        draft, local_editor_revision = _local_workspace_state(
            draft_data,
            editor_revision,
            principal,
        )
        source_revision = _source_revision(revision_state)
        verification = _safe_source_verification(verification_data, draft)
        lifecycle = resolve_manager_lifecycle(
            draft=draft,
            editor_revision=local_editor_revision,
            source_revision=source_revision,
            validation_current=_validation_is_current(draft, validation_data),
            source_verification=verification,
        )
        discardable_local_work = lifecycle.can_discard_local
        conflict_content = None
        if lifecycle.source_conflict and draft is not None and verification is not None:
            conflict_content = build_source_conflict_content(
                draft=draft,
                verification=verification,
            )
        return (
            build_workflow_draft_content(
                draft=draft,
                validation=None if lifecycle.dirty else validation_data,
                source_verification=None if lifecycle.dirty else verification,
                editor_dirty=lifecycle.dirty,
                principal=principal,
                source_revision=source_revision,
            ),
            not lifecycle.can_save_draft,
            not lifecycle.can_validate,
            not lifecycle.can_verify_source,
            not lifecycle.can_publish,
            not discardable_local_work,
            not lifecycle.source_conflict,
            conflict_content,
            not lifecycle.can_force_publish,
        )

    @app.callback(
        Output(workflow_saved_draft_status_id(MATCH), 'children'),
        Output(workflow_action_id(MATCH, 'recover-saved-draft'), 'disabled'),
        Output(workflow_action_id(MATCH, 'discard-saved-draft'), 'disabled'),
        Input(workflow_saved_draft_id(MATCH), 'data'),
        Input(workflow_revision_id(MATCH), 'data'),
    )
    def refresh_saved_draft_status(
        saved_draft_data: dict[str, object] | None,
        revision_state: dict[str, object] | None,
    ):
        if saved_draft_data is None:
            return build_saved_draft_content(draft=None, source_revision=None), True, True
        principal = definition.principal_provider()
        try:
            draft = _require_draft(saved_draft_data, principal)
        except ManagerError:
            return (
                build_saved_draft_content(
                    draft=None,
                    source_revision=_source_revision(revision_state),
                    incompatible=True,
                ),
                True,
                False,
            )
        return (
            build_saved_draft_content(
                draft=draft,
                source_revision=_source_revision(revision_state),
            ),
            False,
            False,
        )

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
        State(workflow_revision_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def manage_saved_browser_draft(
        recover_clicks: int | None,
        discard_clicks: int | None,
        saved_draft_data: dict[str, object] | None,
        revision_state: dict[str, object] | None,
    ):
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
        try:
            draft = _require_draft(saved_draft_data, principal)
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update, no_update
        source_revision = _source_revision(revision_state)
        source_changed = draft.base_source_revision != source_revision
        message = (
            'Borrador recuperado. La fuente cambió desde que se guardó; revisa el contenido '
            'y verifica la fuente antes de publicar.'
            if source_changed
            else 'Borrador recuperado en el workspace local.'
        )
        return (
            _notice_message(message),
            draft.to_document(),
            no_update,
            None,
            None,
            draft.revision,
        )

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'validate'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def validate_configuration(
        clicks: int,
        draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        principal = definition.principal_provider()
        try:
            draft = _require_draft(draft_data, principal)
            if _editor_revision(editor_revision) != draft.revision:
                raise ManagerProjectionError(
                    'Current editor changes must be saved before validation'
                )
            result = coordinator.validate_draft(
                str(trigger.get('module', '')),
                principal,
                draft.payload,
            )
            if result.draft_revision != draft.revision:
                raise ManagerProjectionError(
                    'Validated draft revision does not match browser draft'
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
        clicks: int,
        draft_data: dict[str, object] | None,
        validation_data: dict[str, object] | None,
        editor_revision: str | None,
        refresh_signal: int | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        principal = definition.principal_provider()
        try:
            draft = _require_draft(draft_data, principal)
            if _editor_revision(editor_revision) != draft.revision:
                raise ManagerProjectionError(
                    'Current editor changes must be saved before verification'
                )
            if not _validation_is_current(draft, validation_data):
                raise ManagerProjectionError('A successful draft validation is required')
            result = coordinator.verify_source(
                str(trigger.get('module', '')),
                principal,
                draft_revision=draft.revision,
                base_source_revision=draft.base_source_revision,
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
        clicks: int,
        draft_data: dict[str, object] | None,
        validation_data: dict[str, object] | None,
        verification_data: dict[str, object] | None,
        editor_revision: str | None,
        refresh_signal: int | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update, no_update, no_update
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', ''))
        try:
            draft = _require_draft(draft_data, principal)
            if _editor_revision(editor_revision) != draft.revision:
                raise ManagerProjectionError(
                    'Current editor changes must be saved before publication'
                )
            if not _validation_is_current(draft, validation_data):
                raise ManagerProjectionError('A successful draft validation is required')
            verification = _require_source_verification(verification_data, draft)
            if not verification.publishable:
                raise ManagerSourceConflictError('Manager source verification detected a conflict')
            result = coordinator.publish_draft(
                module_key,
                principal,
                draft.payload,
                verification.source_revision,
            )
            updated_draft = draft.with_base_source_revision(result.source_revision)
        except ManagerSourceConflictError:
            refreshed_verification = _refresh_source_verification(
                coordinator=coordinator,
                module_key=module_key,
                principal=principal,
                draft_data=draft_data,
            )
            return (
                _notice_message(
                    'La fuente cambió antes de completar la publicación. '
                    'Revisa el detalle antes de continuar.'
                ),
                int(refresh_signal or 0) + 1,
                no_update,
                no_update,
                refreshed_verification,
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
        return (
            None,
            int(refresh_signal or 0) + 1,
            updated_draft.to_document(),
            None,
            None,
        )

    @app.callback(
        Output(workflow_result_id(MATCH), 'children'),
        Output(workflow_draft_id(MATCH), 'data'),
        Output(workflow_validation_id(MATCH), 'data'),
        Output(workflow_source_verification_id(MATCH), 'data'),
        Input(workflow_revision_id(MATCH), 'data'),
        State(workflow_revision_id(MATCH), 'id'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
    )
    def hydrate_source_workspace(
        revision_state: dict[str, object] | None,
        revision_id: dict[str, object],
        draft_data: dict[str, object] | None,
        editor_revision: str | None,
    ):
        trigger = ctx.triggered_id
        if trigger is not None and not (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-manager-workflow-revision'
        ):
            return no_update, no_update, no_update, no_update
        principal = definition.principal_provider()
        if _has_local_work(draft_data, editor_revision, principal):
            return no_update, no_update, no_update, no_update
        if _source_revision(revision_state) is None:
            return no_update, no_update, no_update, no_update
        module_key = str((trigger if isinstance(trigger, dict) else revision_id).get('module', ''))
        try:
            snapshot = coordinator.load_current_source(
                module_key,
                principal,
            )
            draft = ManagerDraft.create(
                owner_subject_id=principal.subject_id,
                payload=snapshot.payload,
                base_source_revision=snapshot.revision,
            )
        except Exception:
            return no_update, no_update, no_update, no_update
        return None, draft.to_document(), None, None

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
        update_clicks: int,
        keep_clicks: int,
        draft_data: dict[str, object] | None,
        verification_data: dict[str, object] | None,
        refresh_signal: int | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            return no_update, no_update, no_update, no_update, no_update
        action = str(trigger.get('action', ''))
        clicks = update_clicks if action == 'update-source' else keep_clicks
        if action not in {'update-source', 'keep-draft'} or not _click_is_real(clicks):
            return no_update, no_update, no_update, no_update, no_update
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', ''))
        try:
            if action == 'keep-draft':
                module = registry.require(module_key)
                draft = _require_draft(draft_data, principal)
                verification = _require_source_verification(verification_data, draft)
                if not verification.conflict or verification.source_revision is None:
                    raise ManagerProjectionError('Manager draft does not have a source conflict')
                updated_draft = draft.with_base_source_revision(verification.source_revision)
                return (
                    _notice_message(
                        f'Tu borrador se conservó. Vuelve a verificar {module.source_name} '
                        'antes de publicar.'
                    ),
                    updated_draft.to_document(),
                    no_update,
                    None,
                    no_update,
                )
            snapshot = coordinator.load_current_source(
                module_key,
                principal,
            )
            draft = ManagerDraft.create(
                owner_subject_id=principal.subject_id,
                payload=snapshot.payload,
                base_source_revision=snapshot.revision,
            )
        except ManagerSourceConflictError:
            return (
                _notice_message(
                    'La fuente volvió a cambiar mientras se actualizaba. '
                    'Revisa la revisión actual e inténtalo nuevamente.'
                ),
                no_update,
                no_update,
                no_update,
                int(refresh_signal or 0) + 1,
            )
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
        return None, draft.to_document(), None, None, int(refresh_signal or 0) + 1

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_saved_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_action_id(MATCH, 'force-publish'), 'n_clicks'),
        State(workflow_draft_id(MATCH), 'data'),
        State(workflow_validation_id(MATCH), 'data'),
        State(workflow_source_verification_id(MATCH), 'data'),
        State(workflow_editor_revision_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def force_publish_configuration(
        clicks: int,
        draft_data: dict[str, object] | None,
        validation_data: dict[str, object] | None,
        verification_data: dict[str, object] | None,
        editor_revision: str | None,
        refresh_signal: int | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update, no_update, no_update
        principal = definition.principal_provider()
        module_key = str(trigger.get('module', ''))
        try:
            draft = _require_draft(draft_data, principal)
            if _editor_revision(editor_revision) != draft.revision:
                raise ManagerProjectionError(
                    'Current editor changes must be saved before publication'
                )
            if not _validation_is_current(draft, validation_data):
                raise ManagerProjectionError('A successful draft validation is required')
            verification = _require_source_verification(verification_data, draft)
            if verification.matches or verification.source_revision is None:
                raise ManagerProjectionError('Manager force publication requires a source conflict')
            result = coordinator.force_publish_draft(
                module_key,
                principal,
                draft.payload,
                base_source_revision=draft.base_source_revision,
                expected_source_revision=verification.source_revision,
            )
            updated_draft = draft.with_base_source_revision(result.source_revision)
        except ManagerSourceConflictError:
            refreshed_verification = _refresh_source_verification(
                coordinator=coordinator,
                module_key=module_key,
                principal=principal,
                draft_data=draft_data,
            )
            return (
                _notice_message(
                    'La fuente volvió a cambiar antes de completar la publicación. '
                    'Revisa el nuevo cambio antes de decidir.'
                ),
                int(refresh_signal or 0) + 1,
                no_update,
                no_update,
                refreshed_verification,
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update
        except Exception:
            return (
                _error_message('Configuration could not be force published'),
                no_update,
                no_update,
                no_update,
                no_update,
            )
        return None, int(refresh_signal or 0) + 1, updated_draft.to_document(), None, None

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
        discard_clicks: int,
        reload_clicks: int,
        confirm_clicks: int,
        cancel_clicks: int,
        draft_data: dict[str, object] | None,
        editor_revision: str | None,
        command: str | None,
        refresh_signal: int | None,
        reset_signal: int | None,
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
        has_local_work = _has_local_work(draft_data, editor_revision, principal)
        module_key = str(trigger.get('module', '')) if isinstance(trigger, dict) else ''
        try:
            module = registry.require(module_key)
        except ManagerError:
            return (no_update,) * 11
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
                (
                    f'Se descartarán los cambios locales y se restaurará la versión actual de '
                    f'{module.source_name}. La fuente de verdad y la proyección runtime no se '
                    'modificarán.'
                ),
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
                (
                    f'Se descartarán los cambios locales, se restaurará la versión actual de '
                    f'{module.source_name} y se volverán a consultar la fuente, el historial y '
                    'la proyección. No se publicará ni proyectará nada.'
                ),
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
            source_workspace = _load_current_source_workspace_draft(
                coordinator=coordinator,
                module_key=module_key,
                principal=principal,
            )
        except ManagerSourceConflictError:
            return (
                True,
                None,
                None,
                None,
                _notice_message(
                    f'{module.source_name} cambió mientras se restauraba el workspace. '
                    'Vuelve a intentarlo.'
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
            message = (
                f'{module.source_name} no tiene una configuración publicada. '
                'El workspace local quedó vacío.'
            )
            draft_output = None
            editor_output = None
            reset_output = int(reset_signal or 0) + 1
        else:
            message = (
                f'Workspace restaurado desde la versión actual de {module.source_name}.'
                if resolved_command == 'discard'
                else f'Estado remoto recargado y workspace actualizado desde {module.source_name}.'
            )
            draft_output = source_workspace.to_document()
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
        Input(
            history_preview_open_id(
                MATCH, ALL, ALL, saved_by=ALL, saved_at=ALL, current=ALL, active=ALL
            ),
            'n_clicks',
        ),
        Input(workflow_history_preview_close_id(MATCH), 'n_clicks'),
        State(
            history_preview_open_id(
                MATCH, ALL, ALL, saved_by=ALL, saved_at=ALL, current=ALL, active=ALL
            ),
            'id',
        ),
        prevent_initial_call=True,
    )
    def manage_history_preview(
        clicks: list[int],
        close_clicks: int,
        preview_ids: list[dict[str, object]],
    ):
        trigger = ctx.triggered_id
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-manager-history-preview-close'
        ):
            if not _click_is_real(close_clicks):
                return (no_update,) * 6
            return True, None, None, None, None, no_update
        if not _pattern_click_is_real(trigger, clicks, preview_ids):
            return (no_update,) * 6
        module_key = str(trigger.get('module', ''))
        revision = str(trigger.get('revision', '')).strip()
        principal = definition.principal_provider()
        try:
            module = registry.require(module_key)
            renderer = module.history_preview_renderer
            if renderer is None:
                raise ManagerProjectionError('Manager module does not support history preview')
            payload = coordinator.load_history_revision(module_key, principal, revision)
            preview = renderer(payload)
        except ManagerError as error:
            return True, None, None, None, None, _error_message(str(error))
        except Exception:
            return (
                True,
                None,
                None,
                None,
                None,
                _error_message('History revision preview could not be loaded'),
            )
        labels = []
        if bool(trigger.get('current')):
            labels.append('Fuente actual')
        if bool(trigger.get('active')):
            labels.append('Proyección activa')
        status = ' · '.join(labels) if labels else 'Histórica'
        metadata = html.Div(
            [
                _history_preview_meta_item('Revisión', revision[:12]),
                _history_preview_meta_item('Publicado por', str(trigger.get('saved_by', '—'))),
                _history_preview_meta_item('Fecha', str(trigger.get('saved_at', '—'))),
                _history_preview_meta_item('Estado', status),
            ],
            className='atlanticus-manager__history-preview-meta-grid',
        )
        preview_state = {
            'schema_version': 1,
            'module_key': module_key,
            'revision': revision,
            'payload': payload,
        }
        return False, f'Revisión {revision[:12]}', metadata, preview, preview_state, None

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_source_verification_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_history_preview_id(MATCH), 'hidden', allow_duplicate=True),
        Output(workflow_history_preview_store_id(MATCH), 'data', allow_duplicate=True),
        Input(workflow_history_preview_load_id(MATCH), 'n_clicks'),
        State(workflow_history_preview_store_id(MATCH), 'data'),
        State(workflow_revision_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def load_history_preview_as_draft(
        clicks: int,
        preview_data: dict[str, object] | None,
        revision_state: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return (no_update,) * 6
        module_key = str(trigger.get('module', ''))
        principal = definition.principal_provider()
        try:
            payload = _history_preview_payload(preview_data, module_key)
            base_source_revision = None
            if revision_state:
                raw = revision_state.get('source_revision')
                base_source_revision = str(raw) if raw else None
            draft = ManagerDraft.create(
                owner_subject_id=principal.subject_id,
                payload=payload,
                base_source_revision=base_source_revision,
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update, no_update, no_update, no_update
        except Exception:
            return (
                _error_message('History revision could not be loaded as a draft'),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        return None, draft.to_document(), None, None, True, None

    @app.callback(
        Output(workflow_result_id(MATCH), 'children', allow_duplicate=True),
        Output(workflow_refresh_signal_id(MATCH), 'data', allow_duplicate=True),
        Output(workflow_projection_signal_id(MATCH), 'data'),
        Input(workflow_action_id(MATCH, 'project'), 'n_clicks'),
        State(workflow_revision_id(MATCH), 'data'),
        State(workflow_refresh_signal_id(MATCH), 'data'),
        prevent_initial_call=True,
    )
    def project_configuration(
        clicks: int,
        revision_state: dict[str, object] | None,
        refresh_signal: int | None,
    ):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not _click_is_real(clicks):
            return no_update, no_update, no_update
        source_revision = None if not revision_state else revision_state.get('source_revision')
        if not source_revision:
            return _error_message('A published source revision is required'), no_update, no_update
        module_key = str(trigger.get('module', ''))
        try:
            result = coordinator.project(
                module_key,
                definition.principal_provider(),
                str(source_revision),
            )
        except ManagerError as error:
            return _error_message(str(error)), no_update, no_update
        except Exception:
            return _error_message('Projection could not be completed'), no_update, no_update
        signal = {
            'source_revision': result.source_revision,
            'projection_revision': result.projection_revision,
        }
        return None, int(refresh_signal or 0) + 1, signal


def _history_preview_meta_item(label: str, value: str) -> object:
    return html.Div(
        [html.Small(label), html.Strong(value)],
        className='atlanticus-manager__history-preview-meta-item',
    )


def _history_preview_payload(
    data: dict[str, object] | None,
    module_key: str,
) -> dict[str, object]:
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ManagerProjectionError('History preview is not available')
    if str(data.get('module_key', '')) != module_key:
        raise ManagerProjectionError('History preview belongs to another module')
    payload = data.get('payload')
    if not isinstance(payload, dict):
        raise ManagerProjectionError('History preview payload is invalid')
    return dict(payload)


def _load_workflow_state(
    coordinator: ManagerProjectionCoordinator,
    module_key: str,
    principal: ManagerPrincipal,
) -> tuple[ProjectionStatus | None, tuple[object, ...], bool, str | None]:
    try:
        status = coordinator.get_status(module_key, principal)
        history = coordinator.list_history(module_key, principal, limit=20)
        can_load_history = coordinator.can_load_history(module_key, principal)
    except ManagerError as error:
        return None, (), False, str(error)
    except Exception:
        return None, (), False, 'Configuration status could not be loaded'
    return status, history, can_load_history, None


def _active_module(
    registry: ManagerModuleRegistry,
    definition: ManagerSurfaceDefinition,
    pathname: str | None,
):
    default_module = registry.require(definition.default_module_key)
    route = pathname or registry.route_for(default_module)
    module = registry.find_by_route(route)
    if module is None and route == registry.root_route:
        module = default_module
    return module


def _safe_draft(
    data: dict[str, object] | None,
    principal: ManagerPrincipal,
) -> ManagerDraft | None:
    try:
        return _require_draft(data, principal)
    except ManagerError:
        return None


def _require_draft(
    data: dict[str, object] | None,
    principal: ManagerPrincipal,
) -> ManagerDraft:
    if not isinstance(data, dict):
        raise ManagerProjectionError('A browser draft is required')
    draft = ManagerDraft.from_document(data)
    if draft.owner_subject_id != principal.subject_id:
        raise ManagerProjectionError('Browser draft belongs to another user')
    return draft


def _validation_is_current(
    draft: ManagerDraft | None,
    validation: dict[str, object] | None,
) -> bool:
    return bool(
        draft is not None
        and validation
        and validation.get('draft_revision') == draft.revision
        and validation.get('valid') is True
    )


def _source_revision(revision_state: dict[str, object] | None) -> str | None:
    if not revision_state:
        return None
    value = revision_state.get('source_revision')
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _editor_revision(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _load_current_source_workspace_draft(
    *,
    coordinator: ManagerProjectionCoordinator,
    module_key: str,
    principal: ManagerPrincipal,
) -> ManagerDraft | None:
    status = coordinator.get_status(module_key, principal)
    if status.source_revision is None:
        return None
    snapshot = coordinator.load_current_source(module_key, principal)
    return ManagerDraft.create(
        owner_subject_id=principal.subject_id,
        payload=snapshot.payload,
        base_source_revision=snapshot.revision,
    )


def _local_workspace_state(
    draft_data: dict[str, object] | None,
    editor_revision: object,
    principal: ManagerPrincipal,
) -> tuple[ManagerDraft | None, str | None]:
    draft = _safe_draft(draft_data, principal)
    if isinstance(draft_data, dict) and draft is None:
        return None, None
    return draft, _editor_revision(editor_revision)


def _has_local_work(
    draft_data: dict[str, object] | None,
    editor_revision: object,
    principal: ManagerPrincipal,
) -> bool:
    draft, local_editor_revision = _local_workspace_state(
        draft_data,
        editor_revision,
        principal,
    )
    if draft is None:
        return local_editor_revision is not None
    if local_editor_revision is not None and local_editor_revision != draft.revision:
        return True
    return draft.revision != draft.base_source_revision


def _safe_source_verification(
    data: dict[str, object] | None,
    draft: ManagerDraft | None,
) -> SourceVerificationResult | None:
    if draft is None or not isinstance(data, dict):
        return None
    try:
        verification = SourceVerificationResult.from_document(data)
    except ManagerError:
        return None
    if verification.draft_revision != draft.revision:
        return None
    return verification


def _require_source_verification(
    data: dict[str, object] | None,
    draft: ManagerDraft,
) -> SourceVerificationResult:
    verification = _safe_source_verification(data, draft)
    if verification is None:
        raise ManagerProjectionError('A current source verification is required')
    return verification


def _refresh_source_verification(
    *,
    coordinator: ManagerProjectionCoordinator,
    module_key: str,
    principal: ManagerPrincipal,
    draft_data: dict[str, object] | None,
) -> dict[str, object] | None:
    try:
        draft = _require_draft(draft_data, principal)
        return coordinator.verify_source(
            module_key,
            principal,
            draft_revision=draft.revision,
            base_source_revision=draft.base_source_revision,
        ).to_document()
    except ManagerError:
        return None


def _issue_document(issue: ProjectionIssue) -> dict[str, object]:
    return {
        'code': issue.code,
        'message': issue.message,
        'level': issue.level,
        'path': issue.path,
    }


def _notice_message(message: str):
    from dash import html

    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--notice',
    )


def _error_message(message: str):
    from dash import html

    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )


def _click_is_real(clicks: int | None) -> bool:
    return isinstance(clicks, int) and not isinstance(clicks, bool) and clicks > 0


def _pattern_click_is_real(
    trigger: object,
    clicks: list[int | None] | None,
    ids: list[dict[str, object]] | None,
) -> bool:
    if not isinstance(trigger, dict):
        return False
    target = dict(trigger)
    for item_id, click_count in zip(ids or [], clicks or [], strict=False):
        if dict(item_id) == target:
            return _click_is_real(click_count)
    return False


def _workflow_revision_state(
    status: ProjectionStatus | None,
) -> dict[str, object] | None:
    if status is None:
        return None
    return {
        'source_revision': status.source_revision,
        'source_actor': status.source_audit.actor if status.source_audit is not None else None,
        'source_occurred_at': (
            status.source_audit.occurred_at.isoformat() if status.source_audit is not None else None
        ),
        'active_source_revision': status.active_source_revision,
    }


def _can_project(status: ProjectionStatus | None) -> bool:
    return bool(
        status
        and status.source_revision
        and status.active_source_revision != status.source_revision
    )


def _safe_state(value: str) -> ProjectionState:
    try:
        return ProjectionState(value)
    except ValueError:
        return ProjectionState.UNAVAILABLE


def _state_label(state: ProjectionState) -> str:
    labels = {
        ProjectionState.NO_SOURCE: 'Sin fuente',
        ProjectionState.SYNCHRONIZED: 'Actualizada',
        ProjectionState.READY: 'Lista',
        ProjectionState.UNAVAILABLE: 'No disponible',
    }
    return labels[state]


def _state_class(state: ProjectionState) -> str:
    return f'atlanticus-manager__state atlanticus-manager__state--{state.value}'


def _panel_class(active: bool) -> str:
    base = 'atlanticus-manager__section-panel'
    return f'{base} {base}--active' if active else base


def _tab_class(active: bool) -> str:
    base = 'atlanticus-manager__tab'
    return f'{base} {base}--active' if active else base
