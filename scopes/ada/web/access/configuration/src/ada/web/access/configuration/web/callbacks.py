from __future__ import annotations

import hashlib
import json

from dash import ALL, Input, Output, State, ctx, html, no_update

from ada.web.access.configuration.editor import (
    create_access_key,
    remove_access_key,
    set_profile_access,
)
from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.web.ids import (
    ACCESS_KEY_INPUT_ID,
    ACCESS_LIST_ID,
    ADD_ACCESS_ID,
    ADD_ACCESS_RESULT_ID,
    APPLY_ASSIGNMENTS_ID,
    ASSIGNMENTS_RESULT_ID,
    CONFIGURATION_STORE_ID,
    MOUNT_STORE_ID,
    PROFILE_ASSIGNMENTS_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
)
from ada.web.access.configuration.web.layout import (
    render_access_catalog,
    render_profile_assignments,
)
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext


def register_ada_access_admin_callbacks(app: object, context: AdaAccessAdminWebContext) -> None:
    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        try:
            payload = context.workspace_payload_reader(draft_data)
            if payload is None:
                return AdaAccessConfiguration().to_document()
            return AdaAccessConfiguration.from_document(dict(payload)).to_document()
        except Exception:
            return AdaAccessConfiguration().to_document()

    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(configuration_data: dict[str, object] | None):
        try:
            return _configuration_digest(_configuration(configuration_data))
        except Exception:
            return None

    @app.callback(
        Output(ACCESS_LIST_ID, 'children'),
        Output(PROFILE_ASSIGNMENTS_ID, 'children'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def render_configuration(configuration_data: dict[str, object] | None):
        configuration = _configuration(configuration_data)
        profiles = context.profile_catalog_provider()
        return (
            render_access_catalog(configuration),
            render_profile_assignments(configuration, profiles),
        )

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(ACCESS_KEY_INPUT_ID, 'value'),
        Output(ADD_ACCESS_RESULT_ID, 'children'),
        Input(ADD_ACCESS_ID, 'n_clicks'),
        State(ACCESS_KEY_INPUT_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_access(
        clicks: int | None,
        access_key: str | None,
        configuration_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            updated = create_access_key(
                _configuration(configuration_data),
                access_key=str(access_key or ''),
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return updated.to_document(), '', None

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(ADD_ACCESS_RESULT_ID, 'children', allow_duplicate=True),
        Input({'type': 'ada-access-admin-remove', 'key': ALL}, 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def remove_access(
        _clicks: list[int | None],
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if (
            not isinstance(trigger, dict)
            or trigger.get('type') != 'ada-access-admin-remove'
            or not _triggered_click_is_real()
        ):
            return no_update, no_update
        if not context.can_manage():
            return no_update, _error('Management access is denied')
        try:
            updated = remove_access_key(
                _configuration(configuration_data),
                access_key=str(trigger['key']),
            )
        except Exception as error:
            return no_update, _error(str(error))
        return updated.to_document(), None

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(ASSIGNMENTS_RESULT_ID, 'children'),
        Input(APPLY_ASSIGNMENTS_ID, 'n_clicks'),
        State({'type': 'ada-access-admin-profile-access', 'profile_key': ALL}, 'value'),
        State({'type': 'ada-access-admin-profile-access', 'profile_key': ALL}, 'id'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def apply_assignments(
        clicks: int | None,
        values: list[list[str] | None],
        ids: list[dict[str, str]],
        configuration_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update
        if not context.can_manage():
            return no_update, _error('Management access is denied')
        try:
            configuration = _configuration(configuration_data)
            for component_id, selected in zip(ids, values, strict=True):
                configuration = set_profile_access(
                    configuration,
                    profile_key=str(component_id['profile_key']),
                    access_keys=tuple(selected or ()),
                )
            profiles = context.profile_catalog_provider()
            if profiles is None:
                raise ValueError('Profiles projection is not available')
            configuration.validate_profiles(profiles)
        except Exception as error:
            return no_update, _error(str(error))
        return configuration.to_document(), None

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_access_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        configuration_data: dict[str, object] | None,
        current_draft: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not _save_draft_click_is_real(
            trigger,
            content_clicks=content_clicks,
            workflow_clicks=workflow_clicks,
            workflow_id=context.draft_save_action_id,
        ):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            payload = _configuration(configuration_data).to_document()
            draft = context.workspace_payload_writer(current_draft, payload)
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return draft, draft, None


def _configuration(data: dict[str, object] | None) -> AdaAccessConfiguration:
    if not isinstance(data, dict):
        raise ValueError('ADA access configuration is not available')
    return AdaAccessConfiguration.from_document(dict(data))


def _configuration_digest(configuration: AdaAccessConfiguration) -> str:
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


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


def _triggered_click_is_real() -> bool:
    triggered = ctx.triggered
    if not triggered:
        return False
    return _click_is_real(triggered[0].get('value'))


def _click_is_real(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _error(message: str) -> object:
    return html.Div(message, className='ada-access-admin__error')
