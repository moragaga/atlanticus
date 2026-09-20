from __future__ import annotations

# Los callbacks mantienen el borrador editable y sincronizan únicamente estado de presentación.
# La vista previa del perfil reacciona al nombre y colores sin modificar el contrato durable.
# La paginación y el modal conservan sus contratos funcionales previos.

import hashlib
import json

from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, DEFAULT_PAGE_SIZE, PageRequest
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
    PAGE_STORE_ID,
    PREVIOUS_PAGE_ID,
    PROFILE_BACKGROUND_COLOR_ID,
    PROFILE_BACKGROUND_COLOR_VALUE_ID,
    PROFILE_CANCEL_ID,
    PROFILE_MODAL_BACKDROP_ID,
    PROFILE_MODAL_CLOSE_ID,
    PROFILE_MODAL_ID,
    PROFILE_MODAL_TITLE_ID,
    PROFILE_NAME_ID,
    PROFILE_PREVIEW_AVATAR_ID,
    PROFILE_PREVIEW_LABEL_ID,
    PROFILE_RESULT_ID,
    PROFILE_SAVE_ID,
    PROFILE_TEXT_COLOR_ID,
    PROFILE_TEXT_COLOR_VALUE_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    profile_page_id,
)
from atlanticus.web.profiles.configuration.web.layout import (
    configured_profiles_page,
    render_configured_profiles,
)
from atlanticus.web.profiles.configuration.web.models import (
    ProfilesAdminWebContext,
    build_profile_avatar_text,
)

_PROFILE_MODAL_CLOSED = 'atlanticus-profiles-admin__modal'
_PROFILE_MODAL_OPEN = (
    'atlanticus-profiles-admin__modal atlanticus-profiles-admin__modal--open'
)


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
        Output(PAGE_STORE_ID, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(PREVIOUS_PAGE_ID, 'n_clicks'),
        Input(NEXT_PAGE_ID, 'n_clicks'),
        Input(profile_page_id(ALL), 'n_clicks'),
        Input(PAGE_SIZE_ID, 'value'),
        State(PAGE_STORE_ID, 'data'),
    )
    def render_profiles(
        configuration_data: dict[str, object] | None,
        previous_clicks: int | None,
        next_clicks: int | None,
        _page_clicks: list[int | None],
        page_size: int | None,
        page_data: dict[str, object] | None,
    ):
        current = _page_request(page_data)
        page_number = current.page_number
        resolved_size = _page_size(page_size)
        trigger = ctx.triggered_id
        if trigger == PREVIOUS_PAGE_ID and _click_is_real(previous_clicks):
            page_number = max(1, page_number - 1)
        elif trigger == NEXT_PAGE_ID and _click_is_real(next_clicks):
            page_number += 1
        elif trigger == PAGE_SIZE_ID:
            page_number = 1
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-profiles-page-number'
            and _triggered_click_is_real()
        ):
            page_number = max(1, int(trigger.get('index', 1)))
        page = configured_profiles_page(
            _configuration(configuration_data),
            PageRequest(page_number=page_number, page_size=resolved_size),
        )
        return (
            render_configured_profiles(page),
            {
                'page_number': page.request.page_number,
                'page_size': page.request.page_size,
            },
        )

    @app.callback(
        Output(EDITOR_STORE_ID, 'data'),
        Output(PROFILE_MODAL_ID, 'className'),
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
            return None, _PROFILE_MODAL_OPEN, 'Nuevo perfil', '', '#123456', '#FFFFFF', None
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
                _PROFILE_MODAL_OPEN,
                'Editar perfil',
                profile.label,
                profile.background_color,
                profile.text_color,
                None,
            )
        return (no_update,) * 7

    @app.callback(
        Output(PROFILE_PREVIEW_AVATAR_ID, 'children'),
        Output(PROFILE_PREVIEW_AVATAR_ID, 'style'),
        Output(PROFILE_PREVIEW_LABEL_ID, 'children'),
        Output(PROFILE_BACKGROUND_COLOR_VALUE_ID, 'children'),
        Output(PROFILE_TEXT_COLOR_VALUE_ID, 'children'),
        Input(PROFILE_NAME_ID, 'value'),
        Input(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        Input(PROFILE_TEXT_COLOR_ID, 'value'),
    )
    def render_profile_preview(
        label: str | None,
        background_color: str | None,
        text_color: str | None,
    ):
        preview_label = str(label or '').strip() or 'Nuevo perfil'
        background = _preview_color(background_color, '#123456')
        text = _preview_color(text_color, '#FFFFFF')
        return (
            build_profile_avatar_text(preview_label),
            {'backgroundColor': background, 'color': text},
            preview_label,
            background,
            text,
        )

    @app.callback(
        Output(PROFILE_MODAL_ID, 'className', allow_duplicate=True),
        Input(PROFILE_CANCEL_ID, 'n_clicks'),
        Input(PROFILE_MODAL_CLOSE_ID, 'n_clicks'),
        Input(PROFILE_MODAL_BACKDROP_ID, 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_profile_editor(
        cancel_clicks: int | None,
        close_clicks: int | None,
        backdrop_clicks: int | None,
    ):
        if (
            _click_is_real(cancel_clicks)
            or _click_is_real(close_clicks)
            or _click_is_real(backdrop_clicks)
        ):
            return _PROFILE_MODAL_CLOSED
        return no_update

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(PROFILE_MODAL_ID, 'className', allow_duplicate=True),
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
        return updated.to_document(), _PROFILE_MODAL_CLOSED, None

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


def _preview_color(value: str | None, fallback: str) -> str:
    candidate = str(value or '').strip().upper()
    if len(candidate) == 7 and candidate.startswith('#'):
        return candidate
    return fallback


def _page_size(value: int | None) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value in ALLOWED_PAGE_SIZES:
        return value
    return DEFAULT_PAGE_SIZE


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
