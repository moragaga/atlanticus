from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.pagination import DEFAULT_PAGE_SIZE
from atlanticus.web.users.web.ids import (
    EDIT_CANCEL_ID,
    EDIT_ENABLED_ID,
    EDIT_IDENTITY_ID,
    EDIT_MODAL_ID,
    EDIT_PROFILE_ID,
    EDIT_RESULT_ID,
    EDIT_SAVE_ID,
    EDIT_SELECTED_ID,
    EDIT_TITLE_ID,
    MANAGED_ENABLED_ID,
    MANAGED_NEXT_ID,
    MANAGED_PAGE_ID,
    MANAGED_PAGE_SIZE_ID,
    MANAGED_PREVIOUS_ID,
    MANAGED_PROFILE_ID,
    MANAGED_ROWS_ID,
    MANAGED_SEARCH_ID,
    MANAGED_STATUS_ID,
    PROMOTION_NEXT_ID,
    PROMOTION_PAGE_ID,
    PROMOTION_PAGE_SIZE_ID,
    PROMOTION_PREVIOUS_ID,
    PROMOTION_RESULT_ID,
    PROMOTION_ROWS_ID,
    PROMOTION_SEARCH_ID,
    PROMOTION_STATE_ID,
    PROMOTION_STATUS_ID,
    REFRESH_ID,
    REFRESH_RESULT_ID,
    SNAPSHOT_ID,
    candidate_profile_id,
    candidate_promote_id,
    managed_edit_id,
)
from atlanticus.web.users.web.layout import (
    identity_details,
    page_status,
    render_managed_rows,
    render_promotion_rows,
)
from atlanticus.web.users.web.models import UsersAdminWebContext
from atlanticus.web.users.web.serialization import preserve_profiles, snapshot_to_document


def register_users_admin_callbacks(app: object, context: UsersAdminWebContext) -> None:
    @app.callback(
        Output(SNAPSHOT_ID, 'data', allow_duplicate=True),
        Output(REFRESH_RESULT_ID, 'children'),
        Input(REFRESH_ID, 'n_clicks'),
        prevent_initial_call=True,
    )
    def refresh_snapshot(clicks):
        if not _click_is_real(clicks):
            return no_update, no_update
        try:
            return snapshot_to_document(context.administration.discover()), _notice('Estado actualizado.')
        except Exception:
            return no_update, _error('No fue posible actualizar Users Administration.')

    @app.callback(
        Output(MANAGED_PROFILE_ID, 'options'),
        Output(EDIT_PROFILE_ID, 'options'),
        Input(SNAPSHOT_ID, 'data'),
    )
    def refresh_profile_options(document):
        options = _profile_options(document)
        return ([{'label': 'Todos los perfiles', 'value': 'all'}, *options], options)

    @app.callback(
        Output(PROMOTION_ROWS_ID, 'children'),
        Output(PROMOTION_STATUS_ID, 'children'),
        Output(PROMOTION_PREVIOUS_ID, 'disabled'),
        Output(PROMOTION_NEXT_ID, 'disabled'),
        Output(PROMOTION_PAGE_ID, 'data'),
        Input(SNAPSHOT_ID, 'data'),
        Input(PROMOTION_SEARCH_ID, 'value'),
        Input(PROMOTION_STATE_ID, 'value'),
        Input(PROMOTION_PAGE_SIZE_ID, 'value'),
        Input(PROMOTION_PREVIOUS_ID, 'n_clicks'),
        Input(PROMOTION_NEXT_ID, 'n_clicks'),
        State(PROMOTION_PAGE_ID, 'data'),
    )
    def render_promotion_page(
        document,
        query,
        state_filter,
        page_size,
        previous_clicks,
        next_clicks,
        current_page,
    ):
        page_number = current_page if isinstance(current_page, int) else 1
        if ctx.triggered_id == PROMOTION_PREVIOUS_ID and _click_is_real(previous_clicks):
            page_number -= 1
        elif ctx.triggered_id == PROMOTION_NEXT_ID and _click_is_real(next_clicks):
            page_number += 1
        elif ctx.triggered_id in {PROMOTION_SEARCH_ID, PROMOTION_STATE_ID, PROMOTION_PAGE_SIZE_ID}:
            page_number = 1
        size = page_size if page_size in (10, 20) else DEFAULT_PAGE_SIZE
        rows, page = render_promotion_rows(
            document,
            query=query,
            state_filter=state_filter,
            page_number=max(1, page_number),
            page_size=size,
            can_manage=context.can_manage(),
        )
        return rows, page_status(page), not page.has_previous, not page.has_next, page.request.page_number

    @app.callback(
        Output(MANAGED_ROWS_ID, 'children'),
        Output(MANAGED_STATUS_ID, 'children'),
        Output(MANAGED_PREVIOUS_ID, 'disabled'),
        Output(MANAGED_NEXT_ID, 'disabled'),
        Output(MANAGED_PAGE_ID, 'data'),
        Input(SNAPSHOT_ID, 'data'),
        Input(MANAGED_SEARCH_ID, 'value'),
        Input(MANAGED_PROFILE_ID, 'value'),
        Input(MANAGED_ENABLED_ID, 'value'),
        Input(MANAGED_PAGE_SIZE_ID, 'value'),
        Input(MANAGED_PREVIOUS_ID, 'n_clicks'),
        Input(MANAGED_NEXT_ID, 'n_clicks'),
        State(MANAGED_PAGE_ID, 'data'),
    )
    def render_managed_page(
        document,
        query,
        profile_filter,
        enabled_filter,
        page_size,
        previous_clicks,
        next_clicks,
        current_page,
    ):
        page_number = current_page if isinstance(current_page, int) else 1
        if ctx.triggered_id == MANAGED_PREVIOUS_ID and _click_is_real(previous_clicks):
            page_number -= 1
        elif ctx.triggered_id == MANAGED_NEXT_ID and _click_is_real(next_clicks):
            page_number += 1
        elif ctx.triggered_id in {
            MANAGED_SEARCH_ID,
            MANAGED_PROFILE_ID,
            MANAGED_ENABLED_ID,
            MANAGED_PAGE_SIZE_ID,
        }:
            page_number = 1
        size = page_size if page_size in (10, 20) else DEFAULT_PAGE_SIZE
        rows, page = render_managed_rows(
            document,
            query=query,
            profile_filter=profile_filter,
            enabled_filter=enabled_filter,
            page_number=max(1, page_number),
            page_size=size,
            can_manage=context.can_manage(),
        )
        return rows, page_status(page), not page.has_previous, not page.has_next, page.request.page_number

    @app.callback(
        Output(SNAPSHOT_ID, 'data', allow_duplicate=True),
        Output(PROMOTION_RESULT_ID, 'children'),
        Input(candidate_promote_id(ALL), 'n_clicks'),
        State(candidate_promote_id(ALL), 'id'),
        State(candidate_profile_id(ALL), 'value'),
        State(candidate_profile_id(ALL), 'id'),
        State(SNAPSHOT_ID, 'data'),
        prevent_initial_call=True,
    )
    def promote_user(clicks, promote_ids, profile_values, profile_ids, document):
        trigger = ctx.triggered_id
        if not _pattern_click_is_real(trigger, clicks, promote_ids) or not context.can_manage():
            return no_update, no_update
        user_id = str(trigger.get('user_id', ''))
        profile_key = _value_for_user(user_id, profile_values, profile_ids)
        if profile_key is None:
            return no_update, _error('Selecciona un profile antes de promover.')
        version = document.get('registry_version') if isinstance(document, dict) else None
        try:
            context.administration.promote(
                user_id,
                profile_key=str(profile_key),
                enabled=True,
                expected_registry_version=version if isinstance(version, str) else None,
            )
            fresh = snapshot_to_document(context.administration.discover())
            return preserve_profiles(fresh, document), _notice('Usuario promovido.')
        except Exception as error:
            return no_update, _error(str(error))

    @app.callback(
        Output(EDIT_MODAL_ID, 'is_open'),
        Output(EDIT_SELECTED_ID, 'data'),
        Output(EDIT_TITLE_ID, 'children'),
        Output(EDIT_IDENTITY_ID, 'children'),
        Output(EDIT_PROFILE_ID, 'value'),
        Output(EDIT_ENABLED_ID, 'value'),
        Output(EDIT_RESULT_ID, 'children'),
        Input(managed_edit_id(ALL), 'n_clicks'),
        Input(EDIT_CANCEL_ID, 'n_clicks'),
        State(managed_edit_id(ALL), 'id'),
        State(SNAPSHOT_ID, 'data'),
        prevent_initial_call=True,
    )
    def manage_edit_modal(edit_clicks, cancel_clicks, edit_ids, document):
        if ctx.triggered_id == EDIT_CANCEL_ID and _click_is_real(cancel_clicks):
            return False, None, None, None, None, [], None
        trigger = ctx.triggered_id
        if not _pattern_click_is_real(trigger, edit_clicks, edit_ids):
            return (no_update,) * 7
        user_id = str(trigger.get('user_id', ''))
        candidate = _candidate(document, user_id)
        user = candidate.get('promoted_user') if candidate is not None else None
        if not isinstance(user, dict):
            return False, None, None, None, None, [], _error('Usuario administrado no disponible.')
        return (
            True,
            user_id,
            f'Editar {user.get("display_name") or user.get("email") or user_id}',
            identity_details(user),
            user.get('profile_key'),
            ['enabled'] if user.get('enabled') is True else [],
            None,
        )

    @app.callback(
        Output(SNAPSHOT_ID, 'data', allow_duplicate=True),
        Output(EDIT_MODAL_ID, 'is_open', allow_duplicate=True),
        Output(EDIT_RESULT_ID, 'children', allow_duplicate=True),
        Input(EDIT_SAVE_ID, 'n_clicks'),
        State(EDIT_SELECTED_ID, 'data'),
        State(EDIT_PROFILE_ID, 'value'),
        State(EDIT_ENABLED_ID, 'value'),
        State(SNAPSHOT_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_user(clicks, user_id, profile_key, enabled_values, document):
        if not _click_is_real(clicks) or not context.can_manage():
            return no_update, no_update, no_update
        if not isinstance(user_id, str) or not isinstance(profile_key, str):
            return no_update, True, _error('Usuario o profile no disponible.')
        version = document.get('registry_version') if isinstance(document, dict) else None
        if not isinstance(version, str):
            return no_update, True, _error('La versión del registry no está disponible. Actualiza antes de guardar.')
        try:
            context.administration.update(
                user_id,
                profile_key=profile_key,
                enabled='enabled' in (enabled_values or []),
                expected_registry_version=version,
            )
            fresh = snapshot_to_document(context.administration.discover())
            return preserve_profiles(fresh, document), False, None
        except Exception as error:
            return no_update, True, _error(str(error))


def _profile_options(document: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(document, dict):
        return []
    profiles = document.get('profiles')
    if not isinstance(profiles, list):
        return []
    return [
        {
            'label': str(profile.get('label') or profile.get('key')),
            'value': profile.get('key'),
        }
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get('key'), str)
    ]


def _candidate(document: dict[str, object] | None, user_id: str) -> dict[str, object] | None:
    if not isinstance(document, dict):
        return None
    values = document.get('candidates')
    if not isinstance(values, list):
        return None
    return next(
        (
            candidate
            for candidate in values
            if isinstance(candidate, dict) and candidate.get('user_id') == user_id
        ),
        None,
    )


def _value_for_user(user_id: str, values, ids):
    for value, item_id in zip(values or [], ids or [], strict=False):
        if isinstance(item_id, dict) and str(item_id.get('user_id', '')) == user_id:
            return value
    return None


def _click_is_real(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _pattern_click_is_real(trigger, clicks, ids) -> bool:
    if not isinstance(trigger, dict):
        return False
    return any(
        isinstance(item_id, dict)
        and dict(item_id) == dict(trigger)
        and _click_is_real(click_count)
        for click_count, item_id in zip(clicks or [], ids or [], strict=False)
    )


def _notice(message: str) -> object:
    return html.Div(message, className='atlanticus-users-admin__notice')


def _error(message: str) -> object:
    return html.Div(message, className='atlanticus-users-admin__error')
