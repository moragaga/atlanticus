from __future__ import annotations

import hashlib
import json

from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.pagination import DEFAULT_PAGE_SIZE, PageRequest
from atlanticus.web.profiles.configuration.editor import create_profile, update_profile
from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
from atlanticus.web.profiles.configuration.web.ids import (
    ADD_PROFILE_ID,
    CONFIGURATION_STORE_ID,
    CONFIGURED_PROFILES_ID,
    EDITOR_STORE_ID,
    MOUNT_STORE_ID,
    NEXT_PAGE_ID,
    PAGE_SIZE_ID,
    PAGE_STATUS_ID,
    PAGE_STORE_ID,
    PREVIOUS_PAGE_ID,
    PROFILE_BACKGROUND_COLOR_ID,
    PROFILE_CANCEL_ID,
    PROFILE_MODAL_ID,
    PROFILE_MODAL_TITLE_ID,
    PROFILE_NAME_ID,
    PROFILE_RESULT_ID,
    PROFILE_SAVE_ID,
    PROFILE_TEXT_COLOR_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
)
from atlanticus.web.profiles.configuration.web.layout import (
    configured_profiles_page,
    page_status,
    render_configured_profiles,
)
from atlanticus.web.profiles.configuration.web.models import ProfilesAdminWebContext


def register_profiles_admin_callbacks(app: object, context: ProfilesAdminWebContext) -> None:
    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        try:
            payload = context.workspace_payload_reader(draft_data)
            if payload is None:
                return ProfilesConfiguration().to_document()
            return ProfilesConfiguration.from_document(dict(payload)).to_document()
        except Exception:
            return ProfilesConfiguration().to_document()

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
        Output(CONFIGURED_PROFILES_ID, 'children'),
        Output(PAGE_STATUS_ID, 'children'),
        Output(PREVIOUS_PAGE_ID, 'disabled'),
        Output(NEXT_PAGE_ID, 'disabled'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(PAGE_STORE_ID, 'data'),
    )
    def render_profiles(
        configuration_data: dict[str, object] | None,
        page_data: dict[str, object] | None,
    ):
        page = configured_profiles_page(
            _configuration(configuration_data),
            _page_request(page_data),
        )
        return (
            render_configured_profiles(page),
            page_status(page),
            not page.has_previous,
            not page.has_next,
        )

    @app.callback(
        Output(PAGE_STORE_ID, 'data'),
        Input(PREVIOUS_PAGE_ID, 'n_clicks'),
        Input(NEXT_PAGE_ID, 'n_clicks'),
        Input(PAGE_SIZE_ID, 'value'),
        State(PAGE_STORE_ID, 'data'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_page(
        previous_clicks: int | None,
        next_clicks: int | None,
        page_size: int | None,
        page_data: dict[str, object] | None,
        configuration_data: dict[str, object] | None,
    ):
        current = _page_request(page_data)
        resolved_size = int(page_size or DEFAULT_PAGE_SIZE)
        trigger = ctx.triggered_id
        if trigger == PAGE_SIZE_ID:
            return {'page_number': 1, 'page_size': resolved_size}

        page = configured_profiles_page(
            _configuration(configuration_data),
            PageRequest(page_number=current.page_number, page_size=resolved_size),
        )
        page_number = page.request.page_number
        if trigger == PREVIOUS_PAGE_ID and _click_is_real(previous_clicks) and page.has_previous:
            page_number -= 1
        elif trigger == NEXT_PAGE_ID and _click_is_real(next_clicks) and page.has_next:
            page_number += 1
        else:
            return no_update
        return {'page_number': page_number, 'page_size': resolved_size}

    @app.callback(
        Output(EDITOR_STORE_ID, 'data'),
        Output(PROFILE_MODAL_ID, 'is_open'),
        Output(PROFILE_MODAL_TITLE_ID, 'children'),
        Output(PROFILE_NAME_ID, 'value'),
        Output(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        Output(PROFILE_TEXT_COLOR_ID, 'value'),
        Output(PROFILE_RESULT_ID, 'children'),
        Input(ADD_PROFILE_ID, 'n_clicks'),
        Input({'type': 'atlanticus-profiles-profile-edit', 'key': ALL}, 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def open_profile_editor(
        add_clicks: int | None,
        _edit_clicks: list[int | None],
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if trigger == ADD_PROFILE_ID and _click_is_real(add_clicks):
            return None, True, 'Nuevo perfil', '', '#123456', '#FFFFFF', None
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-profiles-profile-edit'
            and _triggered_click_is_real()
        ):
            profile = _find_profile(
                _configuration(configuration_data),
                str(trigger['key']),
            )
            if profile is None:
                return (no_update,) * 7
            return (
                {'key': profile.key},
                True,
                'Editar perfil',
                profile.label,
                profile.background_color,
                profile.text_color,
                None,
            )
        return (no_update,) * 7

    @app.callback(
        Output(PROFILE_MODAL_ID, 'is_open', allow_duplicate=True),
        Input(PROFILE_CANCEL_ID, 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_profile_editor(clicks: int | None):
        if _click_is_real(clicks):
            return False
        return no_update

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(PROFILE_MODAL_ID, 'is_open', allow_duplicate=True),
        Output(PROFILE_RESULT_ID, 'children', allow_duplicate=True),
        Input(PROFILE_SAVE_ID, 'n_clicks'),
        State(EDITOR_STORE_ID, 'data'),
        State(PROFILE_NAME_ID, 'value'),
        State(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        State(PROFILE_TEXT_COLOR_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_profile(
        clicks: int | None,
        editor: dict[str, object] | None,
        label: str | None,
        background_color: str | None,
        text_color: str | None,
        configuration_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            configuration = _configuration(configuration_data)
            key = _editor_key(editor)
            if key is None:
                updated = create_profile(
                    configuration,
                    label=str(label or ''),
                    background_color=str(background_color or ''),
                    text_color=str(text_color or ''),
                )
            else:
                updated = update_profile(
                    configuration,
                    key=key,
                    label=str(label or ''),
                    background_color=str(background_color or ''),
                    text_color=str(text_color or ''),
                )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return updated.to_document(), False, None

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
    def save_profiles_draft(
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


def _configuration(data: dict[str, object] | None) -> ProfilesConfiguration:
    if not isinstance(data, dict):
        raise ValueError('Profiles configuration is not available')
    return ProfilesConfiguration.from_document(dict(data))


def _configuration_digest(configuration: ProfilesConfiguration) -> str:
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _page_request(data: dict[str, object] | None) -> PageRequest:
    if not isinstance(data, dict):
        return PageRequest()
    try:
        return PageRequest(
            page_number=int(data.get('page_number', 1)),
            page_size=int(data.get('page_size', DEFAULT_PAGE_SIZE)),
        )
    except (TypeError, ValueError):
        return PageRequest()


def _find_profile(configuration: ProfilesConfiguration, key: str):
    normalized = key.strip().casefold()
    return next((profile for profile in configuration.profiles if profile.key == normalized), None)


def _editor_key(editor: dict[str, object] | None) -> str | None:
    if not isinstance(editor, dict):
        return None
    value = editor.get('key')
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    return normalized or None


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
    return html.Div(message, className='atlanticus-profiles-admin__error')
