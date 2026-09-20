# Los callbacks editan directamente AdaAccessConfiguration.
# El editor de perfil sólo abre cuando existe un catálogo de accesos y recoge el valor de cada dbc.Checkbox.
# Paginar no pierde asignaciones porque no existe un overlay de estado adicional.

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
    ACCESS_KEY_PREVIEW_ID,
    ACCESS_LIST_ID,
    ACCESS_NEXT_ID,
    ACCESS_PAGE_SIZE_ID,
    ACCESS_PAGE_STORE_ID,
    ACCESS_PANEL_ID,
    ACCESS_PERMISSION_INPUT_ID,
    ACCESS_PREVIOUS_ID,
    ACCESS_SCOPE_INPUT_ID,
    ACCESS_TAB_ID,
    ADD_ACCESS_ID,
    ADD_ACCESS_RESULT_ID,
    CONFIGURATION_STORE_ID,
    MOUNT_STORE_ID,
    PROFILE_ASSIGNMENTS_ID,
    PROFILE_EDITOR_STORE_ID,
    PROFILE_MODAL_ACCESS_LIST_ID,
    PROFILE_MODAL_BACKDROP_ID,
    PROFILE_MODAL_CANCEL_ID,
    PROFILE_MODAL_CLOSE_ID,
    PROFILE_MODAL_ID,
    PROFILE_MODAL_RESULT_ID,
    PROFILE_MODAL_SAVE_ID,
    PROFILE_MODAL_TITLE_ID,
    PROFILE_NEXT_ID,
    PROFILE_PAGE_SIZE_ID,
    PROFILE_PAGE_STORE_ID,
    PROFILE_PREVIOUS_ID,
    PROFILES_PANEL_ID,
    PROFILES_TAB_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    VIEW_STORE_ID,
    access_page_id,
    profile_configure_id,
    profile_modal_access_id,
    profile_page_id,
)
from ada.web.access.configuration.web.layout import (
    access_catalog_page,
    profile_assignment_page,
    render_access_catalog,
    render_profile_access_editor,
    render_profile_assignments,
)
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext
from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, DEFAULT_PAGE_SIZE, PageRequest
from atlanticus.web.profiles.models import ProfileCatalog

_PROFILE_MODAL_CLOSED = 'ada-access-admin__modal'
_PROFILE_MODAL_OPEN = 'ada-access-admin__modal ada-access-admin__modal--open'


def register_ada_access_admin_callbacks(app: object, context: AdaAccessAdminWebContext) -> None:
    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
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
        Output(VIEW_STORE_ID, 'data'),
        Output(ACCESS_PANEL_ID, 'className'),
        Output(PROFILES_PANEL_ID, 'className'),
        Output(ACCESS_TAB_ID, 'className'),
        Output(PROFILES_TAB_ID, 'className'),
        Input(ACCESS_TAB_ID, 'n_clicks'),
        Input(PROFILES_TAB_ID, 'n_clicks'),
        State(VIEW_STORE_ID, 'data'),
    )
    def switch_configuration_view(
        _access_clicks: int | None,
        _profile_clicks: int | None,
        current_view: str | None,
    ):
        selected = current_view if current_view in {'accesses', 'profiles'} else 'accesses'
        if ctx.triggered_id == ACCESS_TAB_ID:
            selected = 'accesses'
        elif ctx.triggered_id == PROFILES_TAB_ID:
            selected = 'profiles'
        access_active = selected == 'accesses'
        return (
            selected,
            _panel_class(access_active),
            _panel_class(not access_active),
            _tab_class(access_active),
            _tab_class(not access_active),
        )

    @app.callback(
        Output(ACCESS_KEY_PREVIEW_ID, 'children'),
        Input(ACCESS_SCOPE_INPUT_ID, 'value'),
        Input(ACCESS_PERMISSION_INPUT_ID, 'value'),
    )
    def preview_access_key(scope: str | None, permission: str | None):
        scope_value = str(scope or '').strip().casefold()
        permission_value = str(permission or '').strip().casefold()
        if not scope_value and not permission_value:
            return 'alarms.view'
        if not scope_value:
            return f'—.{permission_value}'
        if not permission_value:
            return f'{scope_value}.—'
        return f'{scope_value}.{permission_value}'

    @app.callback(
        Output(ACCESS_LIST_ID, 'children'),
        Output(ACCESS_PAGE_STORE_ID, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(ACCESS_PREVIOUS_ID, 'n_clicks'),
        Input(ACCESS_NEXT_ID, 'n_clicks'),
        Input(access_page_id(ALL), 'n_clicks'),
        Input(ACCESS_PAGE_SIZE_ID, 'value'),
        State(ACCESS_PAGE_STORE_ID, 'data'),
    )
    def render_accesses(
        configuration_data: dict[str, object] | None,
        previous_clicks: int | None,
        next_clicks: int | None,
        _page_clicks: list[int | None],
        page_size: int | None,
        current_page: int | None,
    ):
        configuration = _configuration(configuration_data)
        page_number = _page_number(current_page)
        trigger = ctx.triggered_id
        if trigger == ACCESS_PREVIOUS_ID and _click_is_real(previous_clicks):
            page_number = max(1, page_number - 1)
        elif trigger == ACCESS_NEXT_ID and _click_is_real(next_clicks):
            page_number += 1
        elif trigger == ACCESS_PAGE_SIZE_ID:
            page_number = 1
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == 'ada-access-admin-access-page-number'
            and _triggered_click_is_real()
        ):
            page_number = max(1, int(trigger.get('index', 1)))
        page = access_catalog_page(
            configuration,
            PageRequest(
                page_number=page_number,
                page_size=_page_size(page_size),
            ),
        )
        return render_access_catalog(page), page.request.page_number

    @app.callback(
        Output(PROFILE_ASSIGNMENTS_ID, 'children'),
        Output(PROFILE_PAGE_STORE_ID, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(PROFILE_PREVIOUS_ID, 'n_clicks'),
        Input(PROFILE_NEXT_ID, 'n_clicks'),
        Input(profile_page_id(ALL), 'n_clicks'),
        Input(PROFILE_PAGE_SIZE_ID, 'value'),
        State(PROFILE_PAGE_STORE_ID, 'data'),
    )
    def render_profiles(
        configuration_data: dict[str, object] | None,
        previous_clicks: int | None,
        next_clicks: int | None,
        _page_clicks: list[int | None],
        page_size: int | None,
        current_page: int | None,
    ):
        configuration = _configuration(configuration_data)
        profiles = context.profile_catalog_provider()
        page_number = _page_number(current_page)
        trigger = ctx.triggered_id
        if trigger == PROFILE_PREVIOUS_ID and _click_is_real(previous_clicks):
            page_number = max(1, page_number - 1)
        elif trigger == PROFILE_NEXT_ID and _click_is_real(next_clicks):
            page_number += 1
        elif trigger == PROFILE_PAGE_SIZE_ID:
            page_number = 1
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == 'ada-access-admin-profile-page-number'
            and _triggered_click_is_real()
        ):
            page_number = max(1, int(trigger.get('index', 1)))
        page = profile_assignment_page(
            profiles,
            PageRequest(
                page_number=page_number,
                page_size=_page_size(page_size),
            ),
        )
        return (
            render_profile_assignments(configuration, page),
            page.request.page_number,
        )

    @app.callback(
        Output(CONFIGURATION_STORE_ID, 'data', allow_duplicate=True),
        Output(ACCESS_SCOPE_INPUT_ID, 'value'),
        Output(ACCESS_PERMISSION_INPUT_ID, 'value'),
        Output(ADD_ACCESS_RESULT_ID, 'children'),
        Input(ADD_ACCESS_ID, 'n_clicks'),
        State(ACCESS_SCOPE_INPUT_ID, 'value'),
        State(ACCESS_PERMISSION_INPUT_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def add_access(
        clicks: int | None,
        scope: str | None,
        permission: str | None,
        configuration_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, no_update, _error('Management access is denied')
        try:
            access_key = _compose_access_key(scope, permission)
            updated = create_access_key(
                _configuration(configuration_data),
                access_key=access_key,
            )
        except Exception as error:
            return no_update, no_update, no_update, _error(str(error))
        return updated.to_document(), '', '', None

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
        Output(PROFILE_EDITOR_STORE_ID, 'data'),
        Output(PROFILE_MODAL_ID, 'className'),
        Output(PROFILE_MODAL_TITLE_ID, 'children'),
        Output(PROFILE_MODAL_ACCESS_LIST_ID, 'children'),
        Output(PROFILE_MODAL_RESULT_ID, 'children'),
        Input(profile_configure_id(ALL), 'n_clicks'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def open_profile_editor(
        _clicks: list[int | None],
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if (
            not isinstance(trigger, dict)
            or trigger.get('type') != 'ada-access-admin-profile-configure'
            or not _triggered_click_is_real()
        ):
            return (no_update,) * 5
        configuration = _configuration(configuration_data)
        if not configuration.access_keys:
            return (no_update,) * 5
        profile_key = str(trigger.get('profile_key', ''))
        try:
            profile = _profile_catalog(context).require(profile_key)
        except Exception as error:
            return no_update, no_update, no_update, no_update, _error(str(error))
        grant = next(
            (item for item in configuration.profile_access if item.profile_key == profile.key),
            None,
        )
        selected = () if grant is None else grant.access_keys
        return (
            {'profile_key': profile.key},
            _PROFILE_MODAL_OPEN,
            f'Accesos · {profile.label}',
            render_profile_access_editor(configuration, selected=selected),
            None,
        )

    @app.callback(
        Output(PROFILE_MODAL_ID, 'className', allow_duplicate=True),
        Input(PROFILE_MODAL_CANCEL_ID, 'n_clicks'),
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
        Output(PROFILE_MODAL_RESULT_ID, 'children', allow_duplicate=True),
        Input(PROFILE_MODAL_SAVE_ID, 'n_clicks'),
        State(PROFILE_EDITOR_STORE_ID, 'data'),
        State(profile_modal_access_id(ALL), 'value'),
        State(profile_modal_access_id(ALL), 'id'),
        State(CONFIGURATION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_profile_assignment(
        clicks: int | None,
        editor: dict[str, object] | None,
        values: list[bool | None],
        ids: list[dict[str, str]],
        configuration_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        profile_key = str((editor or {}).get('profile_key', ''))
        selected = tuple(
            str(component_id['key'])
            for component_id, is_selected in zip(ids, values, strict=True)
            if bool(is_selected)
        )
        try:
            updated = set_profile_access(
                _configuration(configuration_data),
                profile_key=profile_key,
                access_keys=selected,
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


def _profile_catalog(context: AdaAccessAdminWebContext) -> ProfileCatalog:
    profiles = context.profile_catalog_provider()
    return profiles if profiles is not None else ProfileCatalog()


def _compose_access_key(scope: str | None, permission: str | None) -> str:
    scope_value = str(scope or '').strip().casefold()
    permission_value = str(permission or '').strip().casefold()
    if not scope_value:
        raise ValueError('Access scope must not be empty')
    if not permission_value:
        raise ValueError('Access permission must not be empty')
    return f'{scope_value}.{permission_value}'


def _page_size(value: int | None) -> int:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value in ALLOWED_PAGE_SIZES
    ):
        return value
    return DEFAULT_PAGE_SIZE


def _page_number(value: int | None) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def _configuration_digest(configuration: AdaAccessConfiguration) -> str:
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _panel_class(active: bool) -> str:
    return (
        'ada-access-admin__tab-panel ada-access-admin__tab-panel--active'
        if active
        else 'ada-access-admin__tab-panel'
    )


def _tab_class(active: bool) -> str:
    return (
        'ada-access-admin__tab ada-access-admin__tab--active'
        if active
        else 'ada-access-admin__tab'
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


def _triggered_click_is_real() -> bool:
    triggered = ctx.triggered
    if not triggered:
        return False
    return _click_is_real(triggered[0].get('value'))


def _click_is_real(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _error(message: str) -> object:
    return html.Div(message, className='ada-access-admin__error')
