# Callbacks canónicos de Users admin.
# El editor opera sobre UsersProfilesConfiguration y persiste UsersProfilesAdminDraft schema 2.
# SourceSnapshot se conserva durante las ediciones locales.
# Un draft schema 1 se descarta y nunca se convierte a schema 2.
# La publicación productiva exact-source no pertenece a este incremento.

from __future__ import annotations

import base64

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.configuration import (
    UserConfiguration,
    UsersProfilesAdminDraft,
    UsersProfilesConfiguration,
    add_pending_user,
    build_profile_key,
    build_users_profiles_admin_revision,
    decode_users_profiles_configuration_import,
    default_users_profiles_configuration,
    delete_functional_profile,
    save_functional_profile,
    update_administrator_colors as update_administrator_configuration_colors,
    update_managed_user,
)
from atlanticus.web.users.configuration.web.ids import (
    ADD_PROFILE_ID,
    ADMINISTRATOR_BACKGROUND_COLOR_ID,
    ADMINISTRATOR_PREVIEW_ID,
    ADMINISTRATOR_TEXT_COLOR_ID,
    CATALOG_STORE_ID,
    DISCOVERED_LIST_ID,
    DISCOVERED_PANEL_ID,
    DISCOVERED_REFRESH_ID,
    DISCOVERED_TAB_ID,
    DRAFT_BASIS_STORE_ID,
    DRAFT_RECOVERY_RESULT_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    MOUNT_STORE_ID,
    PROFILE_BACKGROUND_COLOR_ID,
    PROFILE_CANCEL_ID,
    PROFILE_EDITOR_STORE_ID,
    PROFILE_KEY_ID,
    PROFILE_MODAL_ID,
    PROFILE_MODAL_TITLE_ID,
    PROFILE_NAME_ID,
    PROFILE_PANEL_ID,
    PROFILE_PREVIEW_ID,
    PROFILE_RESULT_ID,
    PROFILE_SAVE_ID,
    PROFILE_TAB_ID,
    PROFILE_TEXT_COLOR_ID,
    PROFILES_LIST_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SECTION_STORE_ID,
    USER_CANCEL_ID,
    USER_EDITOR_STORE_ID,
    USER_EMAIL_ID,
    USER_ENABLED_ID,
    USER_MODAL_ID,
    USER_MODAL_TITLE_ID,
    USER_NAME_ID,
    USER_PROFILE_ID,
    USER_RESULT_ID,
    USER_SAVE_ID,
    USERS_LIST_ID,
    USERS_PANEL_ID,
    USERS_TAB_ID,
    discovered_add_id,
    profile_delete_id,
    profile_edit_id,
    user_edit_id,
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.models import PendingUserRecord

_MODAL_CLOSED = 'atlanticus-users-admin__modal'
_MODAL_OPEN = 'atlanticus-users-admin__modal atlanticus-users-admin__modal--open'
_PANEL = 'atlanticus-users-admin__panel'
_PANEL_ACTIVE = 'atlanticus-users-admin__panel atlanticus-users-admin__panel--active'
_TAB = 'nav-link atlanticus-users-admin__tab'
_TAB_ACTIVE = (
    'nav-link active atlanticus-users-admin__tab '
    'atlanticus-users-admin__tab--active'
)
_DEFAULT_PROFILE_BACKGROUND_COLOR = '#C9A24B'
_DEFAULT_PROFILE_TEXT_COLOR = '#071522'
_INCOMPATIBLE_DRAFT_DISCARDED_MESSAGE = (
    'El borrador local guardado usa un contrato incompatible y fue descartado. '
    'Se cargó una base limpia desde la fuente actual.'
)


def register_users_admin_callbacks(app: object, context: UsersAdminWebContext) -> None:
    @app.callback(
        Output(CATALOG_STORE_ID, 'data'),
        Output(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value'),
        Output(ADMINISTRATOR_TEXT_COLOR_ID, 'value'),
        Output(DRAFT_BASIS_STORE_ID, 'data'),
        Output(DRAFT_RECOVERY_RESULT_ID, 'children'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        owner = context.draft_owner_provider()
        recovery_message = None
        try:
            if draft_data is None:
                draft = context.administration.create_draft(owner_subject_id=owner)
            else:
                try:
                    draft = _draft(draft_data, owner_subject_id=owner)
                except Exception:
                    draft = context.administration.create_draft(owner_subject_id=owner)
                    recovery_message = _notice(_INCOMPATIBLE_DRAFT_DISCARDED_MESSAGE)
        except Exception as error:
            configuration = default_users_profiles_configuration()
            administrator = _administrator(configuration)
            return (
                configuration.to_document(),
                administrator.background_color,
                administrator.text_color,
                None,
                _error(str(error)),
            )
        administrator = _administrator(draft.configuration)
        return (
            draft.configuration.to_document(),
            administrator.background_color,
            administrator.text_color,
            draft.to_document(),
            recovery_message,
        )

    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(configuration_data: dict[str, object] | None):
        try:
            return build_users_profiles_admin_revision(_configuration(configuration_data))
        except Exception:
            return None

    @app.callback(
        Output(SECTION_STORE_ID, 'data'),
        Input(PROFILE_TAB_ID, 'n_clicks'),
        Input(USERS_TAB_ID, 'n_clicks'),
        Input(DISCOVERED_TAB_ID, 'n_clicks'),
        State(SECTION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def select_editor_section(
        profile_clicks: int | None,
        users_clicks: int | None,
        pending_clicks: int | None,
        current: str | None,
    ):
        trigger = ctx.triggered_id
        values = {
            PROFILE_TAB_ID: ('profiles', profile_clicks),
            USERS_TAB_ID: ('users', users_clicks),
            DISCOVERED_TAB_ID: ('discovered', pending_clicks),
        }
        if trigger not in values:
            return current or 'profiles'
        section, clicks = values[trigger]
        return section if _click_is_real(clicks) else current or 'profiles'

    @app.callback(
        Output(PROFILE_PANEL_ID, 'className'),
        Output(USERS_PANEL_ID, 'className'),
        Output(DISCOVERED_PANEL_ID, 'className'),
        Output(PROFILE_TAB_ID, 'className'),
        Output(USERS_TAB_ID, 'className'),
        Output(DISCOVERED_TAB_ID, 'className'),
        Input(SECTION_STORE_ID, 'data'),
    )
    def render_editor_section(section: str | None):
        selected = section or 'profiles'
        return (
            _PANEL_ACTIVE if selected == 'profiles' else _PANEL,
            _PANEL_ACTIVE if selected == 'users' else _PANEL,
            _PANEL_ACTIVE if selected == 'discovered' else _PANEL,
            _TAB_ACTIVE if selected == 'profiles' else _TAB,
            _TAB_ACTIVE if selected == 'users' else _TAB,
            _TAB_ACTIVE if selected == 'discovered' else _TAB,
        )

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(ADMINISTRATOR_PREVIEW_ID, 'style'),
        Input(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value'),
        Input(ADMINISTRATOR_TEXT_COLOR_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_administrator_colors(
        background_color: str | None,
        text_color: str | None,
        configuration_data: dict[str, object] | None,
    ):
        configuration = _configuration(configuration_data)
        administrator = _administrator(configuration)
        try:
            updated = update_administrator_configuration_colors(
                configuration,
                background_color=background_color or administrator.background_color,
                text_color=text_color or administrator.text_color,
            )
        except Exception:
            return no_update, no_update
        updated_administrator = _administrator(updated)
        return (
            updated.to_document(),
            _profile_preview_style(
                updated_administrator.background_color,
                updated_administrator.text_color,
            ),
        )

    @app.callback(
        Output(PROFILES_LIST_ID, 'children'),
        Output(USERS_LIST_ID, 'children'),
        Input(CATALOG_STORE_ID, 'data'),
    )
    def render_configuration(configuration_data: dict[str, object] | None):
        configuration = _configuration(configuration_data)
        return _profile_cards(configuration), _user_cards(configuration)

    @app.callback(
        Output(DISCOVERED_LIST_ID, 'children'),
        Input(CATALOG_STORE_ID, 'data'),
        Input(DISCOVERED_REFRESH_ID, 'n_clicks'),
    )
    def render_pending_users(
        configuration_data: dict[str, object] | None,
        _refresh_clicks: int | None,
    ):
        configuration = _configuration(configuration_data)
        try:
            pending = context.administration.list_pending(configuration)
        except Exception:
            return _notice('No fue posible actualizar las identidades pendientes.')
        return _pending_cards(pending)

    @app.callback(
        Output(PROFILE_MODAL_ID, 'className'),
        Output(PROFILE_EDITOR_STORE_ID, 'data'),
        Output(PROFILE_MODAL_TITLE_ID, 'children'),
        Output(PROFILE_NAME_ID, 'value'),
        Output(PROFILE_KEY_ID, 'children'),
        Output(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        Output(PROFILE_TEXT_COLOR_ID, 'value'),
        Output(PROFILE_RESULT_ID, 'children'),
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Input(ADD_PROFILE_ID, 'n_clicks'),
        Input(profile_edit_id(ALL), 'n_clicks'),
        Input(PROFILE_CANCEL_ID, 'n_clicks'),
        Input(PROFILE_CANCEL_ID + '-header', 'n_clicks'),
        Input(PROFILE_CANCEL_ID + '-footer', 'n_clicks'),
        Input(PROFILE_SAVE_ID, 'n_clicks'),
        State(profile_edit_id(ALL), 'id'),
        State(PROFILE_EDITOR_STORE_ID, 'data'),
        State(PROFILE_NAME_ID, 'value'),
        State(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        State(PROFILE_TEXT_COLOR_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def profile_editor(
        add_clicks: int | None,
        edit_clicks: list[int | None] | None,
        cancel_clicks: int | None,
        header_cancel_clicks: int | None,
        footer_cancel_clicks: int | None,
        save_clicks: int | None,
        edit_ids: list[dict[str, object]] | None,
        editor_data: dict[str, object] | None,
        name: str | None,
        background_color: str | None,
        text_color: str | None,
        configuration_data: dict[str, object] | None,
    ):
        del cancel_clicks, header_cancel_clicks, footer_cancel_clicks
        trigger = ctx.triggered_id
        configuration = _configuration(configuration_data)
        if _matches_trigger(
            trigger,
            PROFILE_CANCEL_ID,
            PROFILE_CANCEL_ID + '-header',
            PROFILE_CANCEL_ID + '-footer',
        ):
            return _profile_modal_response(closed=True)
        if trigger == ADD_PROFILE_ID and _click_is_real(add_clicks):
            return _profile_modal_response(
                editor={'mode': 'create'},
                title='Nuevo perfil',
                name='',
                key='Se genera al guardar',
                background_color=_DEFAULT_PROFILE_BACKGROUND_COLOR,
                text_color=_DEFAULT_PROFILE_TEXT_COLOR,
            )
        if _pattern_click_is_real(trigger, edit_clicks, edit_ids):
            key = str(trigger.get('key', ''))
            profile = next(
                (
                    item
                    for item in configuration.profiles.profiles
                    if item.key == key and item.key != 'administrator'
                ),
                None,
            )
            if profile is None:
                return _profile_modal_response(error='Profile does not exist')
            return _profile_modal_response(
                editor={'mode': 'edit', 'key': profile.key},
                title='Editar perfil',
                name=profile.label,
                key=profile.key,
                background_color=profile.background_color,
                text_color=profile.text_color,
            )
        if trigger != PROFILE_SAVE_ID or not _click_is_real(save_clicks):
            return _profile_modal_response(no_change=True)
        if not context.can_manage():
            return _profile_modal_response(
                editor=editor_data,
                title=_profile_editor_title(editor_data),
                name=name,
                key=_profile_editor_key(editor_data, name),
                background_color=background_color,
                text_color=text_color,
                error='Management access is denied',
            )
        try:
            updated = _save_profile(
                configuration,
                editor_data,
                name,
                background_color,
                text_color,
            )
        except Exception as error:
            return _profile_modal_response(
                editor=editor_data,
                title=_profile_editor_title(editor_data),
                name=name,
                key=_profile_editor_key(editor_data, name),
                background_color=background_color,
                text_color=text_color,
                error=str(error),
            )
        return _profile_modal_response(closed=True, configuration=updated.to_document())

    @app.callback(
        Output(PROFILE_PREVIEW_ID, 'children'),
        Output(PROFILE_PREVIEW_ID, 'style'),
        Input(PROFILE_NAME_ID, 'value'),
        Input(PROFILE_BACKGROUND_COLOR_ID, 'value'),
        Input(PROFILE_TEXT_COLOR_ID, 'value'),
    )
    def render_profile_preview(
        name: str | None,
        background_color: str | None,
        text_color: str | None,
    ):
        label = str(name or '').strip() or 'Perfil'
        return (
            [
                html.Span(
                    label[:1].upper(),
                    className='atlanticus-users-admin__profile-avatar',
                ),
                html.Strong(label),
            ],
            _profile_preview_style(
                background_color or _DEFAULT_PROFILE_BACKGROUND_COLOR,
                text_color or _DEFAULT_PROFILE_TEXT_COLOR,
            ),
        )

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Input(profile_delete_id(ALL), 'n_clicks'),
        State(profile_delete_id(ALL), 'id'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def delete_profile(
        clicks: list[int | None] | None,
        delete_ids: list[dict[str, object]] | None,
        configuration_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not _pattern_click_is_real(trigger, clicks, delete_ids):
            return no_update
        if not context.can_manage():
            return no_update
        key = str(trigger.get('key', ''))
        configuration = _configuration(configuration_data)
        if any(user.profile_key == key for user in configuration.users.users):
            return no_update
        try:
            return delete_functional_profile(configuration, key).to_document()
        except Exception:
            return no_update

    @app.callback(
        Output(USER_MODAL_ID, 'className'),
        Output(USER_EDITOR_STORE_ID, 'data'),
        Output(USER_MODAL_TITLE_ID, 'children'),
        Output(USER_NAME_ID, 'value'),
        Output(USER_EMAIL_ID, 'value'),
        Output(USER_PROFILE_ID, 'options'),
        Output(USER_PROFILE_ID, 'value'),
        Output(USER_ENABLED_ID, 'value'),
        Output(USER_NAME_ID, 'disabled'),
        Output(USER_EMAIL_ID, 'disabled'),
        Output(USER_RESULT_ID, 'children'),
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Input(user_edit_id(ALL), 'n_clicks'),
        Input(discovered_add_id(ALL), 'n_clicks'),
        Input(USER_CANCEL_ID, 'n_clicks'),
        Input(USER_CANCEL_ID + '-header', 'n_clicks'),
        Input(USER_CANCEL_ID + '-footer', 'n_clicks'),
        Input(USER_SAVE_ID, 'n_clicks'),
        State(user_edit_id(ALL), 'id'),
        State(discovered_add_id(ALL), 'id'),
        State(USER_EDITOR_STORE_ID, 'data'),
        State(USER_NAME_ID, 'value'),
        State(USER_EMAIL_ID, 'value'),
        State(USER_PROFILE_ID, 'value'),
        State(USER_ENABLED_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def user_editor(
        edit_clicks: list[int | None] | None,
        pending_clicks: list[int | None] | None,
        cancel_clicks: int | None,
        header_cancel_clicks: int | None,
        footer_cancel_clicks: int | None,
        save_clicks: int | None,
        edit_ids: list[dict[str, object]] | None,
        pending_ids: list[dict[str, object]] | None,
        editor_data: dict[str, object] | None,
        name: str | None,
        email: str | None,
        profile_key: str | None,
        enabled_value: bool | None,
        configuration_data: dict[str, object] | None,
    ):
        del cancel_clicks, header_cancel_clicks, footer_cancel_clicks
        trigger = ctx.triggered_id
        configuration = _configuration(configuration_data)
        options = _assignable_profile_options(configuration)
        if _matches_trigger(
            trigger,
            USER_CANCEL_ID,
            USER_CANCEL_ID + '-header',
            USER_CANCEL_ID + '-footer',
        ):
            return _user_modal_response(closed=True, options=options)
        if _pattern_click_is_real(trigger, edit_clicks, edit_ids):
            user_id = str(trigger.get('user_id', ''))
            user = next(
                (item for item in configuration.users.users if item.user_id == user_id),
                None,
            )
            if user is None:
                return _user_modal_response(options=options, error='User does not exist')
            return _user_modal_response(
                editor={
                    'mode': 'edit',
                    'user_id': user.user_id,
                    'issuer': user.issuer,
                    'subject_id': user.subject_id,
                },
                title='Editar usuario',
                name=user.display_name,
                email=user.email,
                options=options,
                profile=user.profile_key,
                enabled=user.enabled,
                identity_locked=True,
            )
        if _pattern_click_is_real(trigger, pending_clicks, pending_ids):
            user_id = str(trigger.get('user_id', ''))
            pending = _find_pending(context, configuration, user_id)
            if pending is None:
                return _user_modal_response(
                    options=options,
                    error='Pending user does not exist',
                )
            return _user_modal_response(
                editor={
                    'mode': 'pending',
                    'user_id': pending.user_id,
                    'issuer': pending.issuer,
                    'subject_id': pending.subject_id,
                },
                title='Incorporar usuario pendiente',
                name=pending.display_name or '',
                email=pending.email or '',
                options=options,
                profile=None,
                enabled=True,
                identity_locked=False,
            )
        if trigger != USER_SAVE_ID or not _click_is_real(save_clicks):
            return _user_modal_response(no_change=True, options=options)
        if not context.can_manage():
            return _user_modal_response(
                editor=editor_data,
                title=_user_editor_title(editor_data),
                name=name,
                email=email,
                options=options,
                profile=profile_key,
                enabled=bool(enabled_value),
                identity_locked=_user_identity_locked(editor_data),
                error='Management access is denied',
            )
        try:
            updated = _save_user(
                context,
                configuration,
                editor_data,
                display_name=name,
                email=email,
                profile_key=profile_key,
                enabled=bool(enabled_value),
            )
        except Exception as error:
            return _user_modal_response(
                editor=editor_data,
                title=_user_editor_title(editor_data),
                name=name,
                email=email,
                options=options,
                profile=profile_key,
                enabled=bool(enabled_value),
                identity_locked=_user_identity_locked(editor_data),
                error=str(error),
            )
        return _user_modal_response(
            closed=True,
            options=_assignable_profile_options(updated),
            configuration=updated.to_document(),
        )

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(DRAFT_BASIS_STORE_ID, 'data', allow_duplicate=True),
        Output(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value', allow_duplicate=True),
        Output(ADMINISTRATOR_TEXT_COLOR_ID, 'value', allow_duplicate=True),
        Output(IMPORT_RESULT_ID, 'children'),
        Input(IMPORT_UPLOAD_ID, 'contents'),
        State(DRAFT_BASIS_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def import_configuration(
        contents: str | None,
        basis_data: dict[str, object] | None,
    ):
        if contents is None:
            return (no_update,) * 5
        if not context.can_manage():
            return (no_update,) * 4 + (_error('Management access is denied'),)
        try:
            if ',' not in contents:
                raise ValueError('Configuration file payload is invalid')
            payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
            configuration = decode_users_profiles_configuration_import(payload)
            basis = _draft(
                basis_data,
                owner_subject_id=context.draft_owner_provider(),
            )
            local_draft = basis.with_configuration(configuration)
            administrator = _administrator(configuration)
        except Exception as error:
            return (no_update,) * 4 + (_error(str(error)),)
        return (
            configuration.to_document(),
            local_draft.to_document(),
            administrator.background_color,
            administrator.text_color,
            None,
        )

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(DRAFT_BASIS_STORE_ID, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        State(DRAFT_BASIS_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_users_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        configuration_data: dict[str, object] | None,
        basis_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not _save_draft_click_is_real(
            trigger,
            content_clicks=content_clicks,
            workflow_clicks=workflow_clicks,
            workflow_id=context.draft_save_action_id,
        ):
            return no_update, no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, no_update, _error('Management access is denied')
        try:
            configuration = _configuration(configuration_data)
            basis = _draft(
                basis_data,
                owner_subject_id=context.draft_owner_provider(),
            )
            draft = basis.with_configuration(configuration)
            document = draft.to_document()
        except Exception as error:
            return no_update, no_update, no_update, _error(str(error))
        return document, document, document, None


def _configuration(data: dict[str, object] | None) -> UsersProfilesConfiguration:
    if not isinstance(data, dict):
        return default_users_profiles_configuration()
    return UsersProfilesConfiguration.from_document(dict(data))


def _draft(
    data: dict[str, object] | None,
    *,
    owner_subject_id: str,
) -> UsersProfilesAdminDraft:
    if not isinstance(data, dict):
        raise ValueError('Users admin draft does not exist')
    draft = UsersProfilesAdminDraft.from_document(dict(data))
    if draft.owner_subject_id != owner_subject_id.strip():
        raise ValueError('Users admin draft belongs to another user')
    return draft


def _administrator(configuration: UsersProfilesConfiguration) -> ProfileDefinition:
    return configuration.profile_catalog().require('administrator')


def _save_profile(
    configuration: UsersProfilesConfiguration,
    editor_data: dict[str, object] | None,
    name: str | None,
    background_color: str | None,
    text_color: str | None,
) -> UsersProfilesConfiguration:
    editor = editor_data or {}
    mode = str(editor.get('mode', '')).strip()
    if mode not in {'create', 'edit'}:
        raise ValueError('Profile editor mode is invalid')
    return save_functional_profile(
        configuration,
        original_key=(
            str(editor.get('key', '')).strip() or None
            if mode == 'edit'
            else None
        ),
        label=str(name or ''),
        background_color=str(background_color or ''),
        text_color=str(text_color or ''),
    )


def _save_user(
    context: UsersAdminWebContext,
    configuration: UsersProfilesConfiguration,
    editor_data: dict[str, object] | None,
    *,
    display_name: str | None,
    email: str | None,
    profile_key: str | None,
    enabled: bool,
) -> UsersProfilesConfiguration:
    editor = editor_data or {}
    mode = str(editor.get('mode', '')).strip()
    selected_profile = str(profile_key or '').strip()
    if mode == 'pending':
        user_id = _required_text(editor.get('user_id'), 'Pending user id is required')
        pending = _find_pending(context, configuration, user_id)
        if pending is None:
            raise ValueError('Pending user does not exist')
        return add_pending_user(
            configuration,
            pending,
            display_name=str(display_name or ''),
            email=_optional_text(email),
            profile_key=selected_profile,
            enabled=enabled,
        )
    if mode != 'edit':
        raise ValueError('User editor mode is invalid')
    user_id = _required_text(editor.get('user_id'), 'User id is required for edit')
    existing = next(
        (item for item in configuration.users.users if item.user_id == user_id),
        None,
    )
    if existing is None:
        raise ValueError('User does not exist')
    updated = UserConfiguration.create(
        user_id=existing.user_id,
        issuer=existing.issuer,
        subject_id=existing.subject_id,
        display_name=str(display_name or ''),
        email=_optional_text(email),
        profile_key=selected_profile,
        enabled=enabled,
    )
    return update_managed_user(configuration, updated)


def _find_pending(
    context: UsersAdminWebContext,
    configuration: UsersProfilesConfiguration,
    user_id: str,
) -> PendingUserRecord | None:
    try:
        return next(
            (
                item
                for item in context.administration.list_pending(configuration)
                if item.user_id == user_id
            ),
            None,
        )
    except Exception:
        return None


def _assignable_profile_options(
    configuration: UsersProfilesConfiguration,
) -> list[dict[str, str]]:
    return [
        {'label': profile.label, 'value': profile.key}
        for profile in configuration.profile_catalog().all()
    ]


def _profile_cards(configuration: UsersProfilesConfiguration) -> object:
    profiles = tuple(
        profile for profile in configuration.profiles.profiles if profile.key != 'administrator'
    )
    if not profiles:
        return _empty('Todavía no hay perfiles funcionales adicionales.')
    used = {user.profile_key for user in configuration.users.users}
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Span(
                                profile.label[:1].upper(),
                                className='atlanticus-users-admin__profile-avatar',
                            ),
                            html.Strong(profile.label),
                        ],
                        className='atlanticus-users-admin__profile-preview',
                        style=_profile_preview_style(
                            profile.background_color,
                            profile.text_color,
                        ),
                    ),
                    html.Div(
                        [
                            dbc.Button(
                                'Editar',
                                id=profile_edit_id(profile.key),
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                                size='sm',
                            ),
                            dbc.Button(
                                'Eliminar',
                                id=profile_delete_id(profile.key),
                                n_clicks=0,
                                disabled=profile.key in used,
                                color='danger',
                                outline=True,
                                size='sm',
                            ),
                        ],
                        className='atlanticus-users-admin__card-actions',
                    ),
                ],
                className='atlanticus-users-admin__list-card',
            )
            for profile in profiles
        ],
        className='atlanticus-users-admin__list',
    )


def _user_cards(configuration: UsersProfilesConfiguration) -> object:
    users = configuration.users.users
    if not users:
        return _empty('Todavía no hay usuarios configurados.')
    profiles = configuration.profile_catalog()
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(user.display_name),
                            html.Span(user.email or 'Sin correo'),
                            html.Code(user.user_id),
                        ],
                        className='atlanticus-users-admin__user-copy',
                    ),
                    html.Div(
                        [
                            _profile_badge(profiles.require(user.profile_key)),
                            html.Span(
                                'Activo' if user.enabled else 'Deshabilitado',
                                className='atlanticus-users-admin__status',
                            ),
                            dbc.Button(
                                'Editar',
                                id=user_edit_id(user.user_id),
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                                size='sm',
                            ),
                        ],
                        className='atlanticus-users-admin__card-actions',
                    ),
                ],
                className='atlanticus-users-admin__list-card',
            )
            for user in users
        ],
        className='atlanticus-users-admin__list',
    )


def _pending_cards(users: tuple[PendingUserRecord, ...]) -> object:
    if not users:
        return _empty('No hay identidades pendientes de incorporación.')
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(user.display_name or 'Identidad pendiente'),
                            html.Span(user.email or 'Sin correo'),
                            html.Code(user.user_id),
                        ],
                        className='atlanticus-users-admin__user-copy',
                    ),
                    dbc.Button(
                        'Incorporar',
                        id=discovered_add_id(user.user_id),
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                    ),
                ],
                className='atlanticus-users-admin__list-card',
            )
            for user in users
        ],
        className='atlanticus-users-admin__list',
    )


def _profile_badge(profile: ProfileDefinition) -> object:
    return html.Span(
        profile.label,
        className='atlanticus-users-admin__profile-badge',
        style={
            'backgroundColor': profile.background_color,
            'color': profile.text_color,
        },
    )


def _profile_preview_style(
    background_color: str,
    text_color: str,
) -> dict[str, str]:
    return {
        '--atlanticus-users-profile-background-color': background_color,
        '--atlanticus-users-profile-text-color': text_color,
    }


def _profile_editor_key(
    editor_data: dict[str, object] | None,
    name: str | None,
) -> str:
    if str((editor_data or {}).get('mode', '')) == 'edit':
        return str((editor_data or {}).get('key', ''))
    try:
        return build_profile_key(str(name or ''))
    except Exception:
        return 'Se genera al guardar'


def _profile_editor_title(editor_data: dict[str, object] | None) -> str:
    return 'Editar perfil' if str((editor_data or {}).get('mode', '')) == 'edit' else 'Nuevo perfil'


def _user_editor_title(editor_data: dict[str, object] | None) -> str:
    mode = str((editor_data or {}).get('mode', 'create'))
    if mode == 'pending':
        return 'Incorporar usuario pendiente'
    if mode == 'edit':
        return 'Editar usuario'
    return 'Usuario'


def _user_identity_locked(editor_data: dict[str, object] | None) -> bool:
    return str((editor_data or {}).get('mode', '')) == 'edit'


def _profile_modal_response(
    *,
    closed: bool = False,
    no_change: bool = False,
    editor: dict[str, object] | None = None,
    title: str | None = None,
    name: str | None = None,
    key: str | None = None,
    background_color: str | None = None,
    text_color: str | None = None,
    error: str | None = None,
    configuration: dict[str, object] | None = None,
):
    if no_change:
        return (no_update,) * 9
    if closed:
        return (
            _MODAL_CLOSED,
            None,
            '',
            '',
            '',
            _DEFAULT_PROFILE_BACKGROUND_COLOR,
            _DEFAULT_PROFILE_TEXT_COLOR,
            None,
            configuration or no_update,
        )
    return (
        _MODAL_OPEN,
        editor,
        title or 'Perfil',
        name or '',
        key or 'Se genera al guardar',
        background_color or _DEFAULT_PROFILE_BACKGROUND_COLOR,
        text_color or _DEFAULT_PROFILE_TEXT_COLOR,
        _error(error) if error else None,
        configuration if configuration is not None else no_update,
    )


def _user_modal_response(
    *,
    closed: bool = False,
    no_change: bool = False,
    editor: dict[str, object] | None = None,
    title: str | None = None,
    name: str | None = None,
    email: str | None = None,
    options: list[dict[str, str]] | None = None,
    profile: str | None = None,
    enabled: bool = True,
    identity_locked: bool = False,
    error: str | None = None,
    configuration: dict[str, object] | None = None,
):
    if no_change:
        return (no_update,) * 12
    if closed:
        return (
            _MODAL_CLOSED,
            None,
            '',
            '',
            '',
            options or [],
            None,
            True,
            False,
            False,
            None,
            configuration or no_update,
        )
    return (
        _MODAL_OPEN,
        editor,
        title or 'Usuario',
        name or '',
        email or '',
        options or [],
        profile,
        bool(enabled),
        identity_locked,
        identity_locked,
        _error(error) if error else None,
        configuration if configuration is not None else no_update,
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
    return False


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


def _matches_trigger(trigger: object, *ids: str) -> bool:
    return isinstance(trigger, str) and trigger in ids


def _required_text(value: object, message: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(message)
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _empty(message: str) -> object:
    return html.Div(message, className='atlanticus-users-admin__empty')


def _notice(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-users-admin__message atlanticus-users-admin__message--notice',
    )


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-users-admin__message atlanticus-users-admin__message--error',
    )
