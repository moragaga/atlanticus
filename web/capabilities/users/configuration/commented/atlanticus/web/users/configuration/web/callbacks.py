# Hidrata Users solo desde el draft explícito del Manager y conserva separada la revisión base asociada al contenido cargado.
# Los cambios del editor informan su propia revisión sin convertir Source en workspace de forma implícita.

from __future__ import annotations

import base64
from datetime import UTC, datetime

from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.users.configuration.bundle import (
    build_users_configuration_digest,
    decode_users_configuration_import,
)
from atlanticus.web.users.configuration.models import (
    DiscoveredUser,
    UserConfiguration,
    UserProfileConfiguration,
    UsersConfigurationCatalog,
    build_profile_key,
)
from atlanticus.web.users.configuration.web.ids import (
    ADD_PROFILE_ID,
    ADD_USER_ID,
    ADMINISTRATOR_BACKGROUND_COLOR_ID,
    ADMINISTRATOR_PREVIEW_ID,
    ADMINISTRATOR_TEXT_COLOR_ID,
    CATALOG_STORE_ID,
    DISCOVERED_LIST_ID,
    DISCOVERED_PANEL_ID,
    DISCOVERED_REFRESH_ID,
    DISCOVERED_TAB_ID,
    GUEST_BACKGROUND_COLOR_ID,
    GUEST_PREVIEW_ID,
    GUEST_TEXT_COLOR_ID,
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
    SOURCE_REVISION_STORE_ID,
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
    color_picker_button_id,
    color_picker_swatch_id,
    discovered_add_id,
    profile_delete_id,
    profile_edit_id,
    user_edit_id,
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.profiles import (
    DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
    DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    DEFAULT_GUEST_BACKGROUND_COLOR,
    DEFAULT_GUEST_TEXT_COLOR,
    ProfileDefinition,
)

_MODAL_CLOSED = 'atlanticus-users-admin__modal'
_MODAL_OPEN = 'atlanticus-users-admin__modal atlanticus-users-admin__modal--open'
_PANEL = 'atlanticus-users-admin__panel'
_PANEL_ACTIVE = 'atlanticus-users-admin__panel atlanticus-users-admin__panel--active'
_TAB = 'atlanticus-users-admin__tab'
_TAB_ACTIVE = 'atlanticus-users-admin__tab atlanticus-users-admin__tab--active'
_DEFAULT_PROFILE_BACKGROUND_COLOR = '#C9A24B'
_DEFAULT_PROFILE_TEXT_COLOR = '#071522'
_BROWSER_DRAFT_SCHEMA_VERSION = 1


def register_users_admin_callbacks(app: object, context: UsersAdminWebContext) -> None:
    for picker_id in (
        ADMINISTRATOR_BACKGROUND_COLOR_ID,
        ADMINISTRATOR_TEXT_COLOR_ID,
        GUEST_BACKGROUND_COLOR_ID,
        GUEST_TEXT_COLOR_ID,
        PROFILE_BACKGROUND_COLOR_ID,
        PROFILE_TEXT_COLOR_ID,
    ):
        _register_native_color_picker(app, picker_id)

    @app.callback(
        Output(CATALOG_STORE_ID, 'data'),
        Output(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value'),
        Output(ADMINISTRATOR_TEXT_COLOR_ID, 'value'),
        Output(GUEST_BACKGROUND_COLOR_ID, 'value'),
        Output(GUEST_TEXT_COLOR_ID, 'value'),
        Output(SOURCE_REVISION_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        if draft_data is None:
            return (no_update,) * 6
        try:
            catalog = _catalog_from_browser_draft(
                draft_data,
                context.draft_owner_provider(),
            )
            base_source_revision = _draft_base_source_revision(
                draft_data,
                owner_subject_id=context.draft_owner_provider(),
                fallback=None,
            )
        except Exception:
            catalog = _empty_catalog()
            return (
                catalog.to_document(),
                catalog.administrator_background_color,
                catalog.administrator_text_color,
                catalog.guest_background_color,
                catalog.guest_text_color,
                None,
            )
        return (
            catalog.to_document(),
            catalog.administrator_background_color,
            catalog.administrator_text_color,
            catalog.guest_background_color,
            catalog.guest_text_color,
            base_source_revision,
        )

    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(catalog_data: dict[str, object] | None):
        try:
            return build_users_configuration_digest(_catalog(catalog_data))
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
        discovered_clicks: int | None,
        current: str | None,
    ):
        trigger = ctx.triggered_id
        values = {
            PROFILE_TAB_ID: ('profiles', profile_clicks),
            USERS_TAB_ID: ('users', users_clicks),
            DISCOVERED_TAB_ID: ('discovered', discovered_clicks),
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
        Output(GUEST_PREVIEW_ID, 'style'),
        Input(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value'),
        Input(ADMINISTRATOR_TEXT_COLOR_ID, 'value'),
        Input(GUEST_BACKGROUND_COLOR_ID, 'value'),
        Input(GUEST_TEXT_COLOR_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def update_system_colors(
        administrator_background_color: str | None,
        administrator_text_color: str | None,
        guest_background_color: str | None,
        guest_text_color: str | None,
        catalog_data: dict[str, object] | None,
    ):
        catalog = _catalog(catalog_data)
        try:
            updated = UsersConfigurationCatalog(
                administrator_background_color=(
                    administrator_background_color or catalog.administrator_background_color
                ),
                administrator_text_color=(
                    administrator_text_color or catalog.administrator_text_color
                ),
                guest_background_color=(guest_background_color or catalog.guest_background_color),
                guest_text_color=guest_text_color or catalog.guest_text_color,
                profiles=catalog.profiles,
                users=catalog.users,
            )
        except Exception:
            return no_update, no_update, no_update
        return (
            updated.to_document(),
            _profile_preview_style(
                updated.administrator_background_color,
                updated.administrator_text_color,
            ),
            _profile_preview_style(
                updated.guest_background_color,
                updated.guest_text_color,
            ),
        )

    @app.callback(
        Output(PROFILES_LIST_ID, 'children'),
        Output(USERS_LIST_ID, 'children'),
        Input(CATALOG_STORE_ID, 'data'),
    )
    def render_catalog(catalog_data: dict[str, object] | None):
        catalog = _catalog(catalog_data)
        return _profile_cards(catalog), _user_cards(catalog)

    @app.callback(
        Output(DISCOVERED_LIST_ID, 'children'),
        Input(CATALOG_STORE_ID, 'data'),
        Input(DISCOVERED_REFRESH_ID, 'n_clicks'),
    )
    def render_discovered_users(
        catalog_data: dict[str, object] | None,
        _refresh_clicks: int | None,
    ):
        catalog = _catalog(catalog_data)
        configured_ids = {user.user_id for user in catalog.users}
        try:
            discovered = context.services.administration.list_discovered()
        except Exception:
            return _error('Discovered users could not be loaded')
        available = tuple(user for user in discovered if user.user_id not in configured_ids)
        return _discovered_cards(available, catalog)

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
        catalog_data: dict[str, object] | None,
    ):
        del cancel_clicks, header_cancel_clicks, footer_cancel_clicks
        trigger = ctx.triggered_id
        catalog = _catalog(catalog_data)
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
            profile = next((item for item in catalog.profiles if item.key == key), None)
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
                title='Editar perfil',
                name=name,
                key=_profile_editor_key(editor_data, name),
                background_color=background_color,
                text_color=text_color,
                error='Management access is denied',
            )
        try:
            updated = _save_profile(
                catalog,
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
        return _profile_modal_response(closed=True, catalog=updated.to_document())

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
        catalog_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not _pattern_click_is_real(trigger, clicks, delete_ids):
            return no_update
        if not context.can_manage():
            return no_update
        key = str(trigger.get('key', ''))
        catalog = _catalog(catalog_data)
        if any(user.profile_key == key for user in catalog.users):
            return no_update
        updated = UsersConfigurationCatalog(
            administrator_background_color=catalog.administrator_background_color,
            administrator_text_color=catalog.administrator_text_color,
            guest_background_color=catalog.guest_background_color,
            guest_text_color=catalog.guest_text_color,
            profiles=tuple(profile for profile in catalog.profiles if profile.key != key),
            users=catalog.users,
        )
        return updated.to_document()

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
        Input(ADD_USER_ID, 'n_clicks'),
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
        add_clicks: int | None,
        edit_clicks: list[int | None] | None,
        discovered_clicks: list[int | None] | None,
        cancel_clicks: int | None,
        header_cancel_clicks: int | None,
        footer_cancel_clicks: int | None,
        save_clicks: int | None,
        edit_ids: list[dict[str, object]] | None,
        discovered_ids: list[dict[str, object]] | None,
        editor_data: dict[str, object] | None,
        name: str | None,
        email: str | None,
        profile_key: str | None,
        enabled_values: list[str] | None,
        catalog_data: dict[str, object] | None,
    ):
        del cancel_clicks, header_cancel_clicks, footer_cancel_clicks
        trigger = ctx.triggered_id
        catalog = _catalog(catalog_data)
        options = _assignable_profile_options(catalog)
        if _matches_trigger(
            trigger,
            USER_CANCEL_ID,
            USER_CANCEL_ID + '-header',
            USER_CANCEL_ID + '-footer',
        ):
            return _user_modal_response(closed=True, options=options)
        if trigger == ADD_USER_ID and _click_is_real(add_clicks):
            return _user_modal_response(
                editor={'mode': 'create'},
                title='Nuevo usuario',
                name='',
                email='',
                options=options,
                profile=None,
                enabled=True,
            )
        if _pattern_click_is_real(trigger, edit_clicks, edit_ids):
            user_id = str(trigger.get('user_id', ''))
            user = next((item for item in catalog.users if item.user_id == user_id), None)
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
            )
        if _pattern_click_is_real(trigger, discovered_clicks, discovered_ids):
            user_id = str(trigger.get('user_id', ''))
            discovered = _find_discovered(context, user_id)
            if discovered is None:
                return _user_modal_response(
                    options=options,
                    error='Discovered user does not exist',
                )
            existing = next(
                (item for item in catalog.users if item.email == discovered.email),
                None,
            )
            return _user_modal_response(
                editor={
                    'mode': 'discovered',
                    'user_id': discovered.user_id,
                    'issuer': discovered.issuer,
                    'subject_id': discovered.subject_id,
                    'replace_user_id': existing.user_id if existing is not None else None,
                },
                title=(
                    'Vincular identidad descubierta'
                    if existing is not None
                    else 'Incorporar usuario descubierto'
                ),
                name=discovered.display_name,
                email=discovered.email,
                options=options,
                profile=existing.profile_key if existing is not None else None,
                enabled=existing.enabled if existing is not None else True,
                identity_locked=True,
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
                enabled='enabled' in (enabled_values or []),
                identity_locked=_user_identity_locked(editor_data),
                error='Management access is denied',
            )
        try:
            discovered = None
            if str((editor_data or {}).get('mode', 'create')) == 'create':
                discovered = _find_discovered_by_email(context, str(email or ''))
            updated = _save_user(
                catalog,
                editor_data,
                display_name=name,
                email=email,
                profile_key=profile_key,
                enabled='enabled' in (enabled_values or []),
                discovered=discovered,
            )
        except Exception as error:
            return _user_modal_response(
                editor=editor_data,
                title=_user_editor_title(editor_data),
                name=name,
                email=email,
                options=options,
                profile=profile_key,
                enabled='enabled' in (enabled_values or []),
                identity_locked=_user_identity_locked(editor_data),
                error=str(error),
            )
        return _user_modal_response(
            closed=True,
            options=_assignable_profile_options(updated),
            catalog=updated.to_document(),
        )

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(ADMINISTRATOR_BACKGROUND_COLOR_ID, 'value', allow_duplicate=True),
        Output(ADMINISTRATOR_TEXT_COLOR_ID, 'value', allow_duplicate=True),
        Output(GUEST_BACKGROUND_COLOR_ID, 'value', allow_duplicate=True),
        Output(GUEST_TEXT_COLOR_ID, 'value', allow_duplicate=True),
        Output(IMPORT_RESULT_ID, 'children'),
        Input(IMPORT_UPLOAD_ID, 'contents'),
        State(SOURCE_REVISION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def import_configuration(
        contents: str | None,
        source_revision: str | None,
    ):
        if contents is None:
            return (no_update,) * 7
        if not context.can_manage():
            return (no_update,) * 6 + (_error('Management access is denied'),)
        try:
            if ',' not in contents:
                raise ValueError('Configuration file payload is invalid')
            payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
            catalog = decode_users_configuration_import(payload)
            draft = _browser_draft_document(
                catalog=catalog,
                owner_subject_id=context.draft_owner_provider(),
                base_source_revision=source_revision,
            )
        except Exception as error:
            return (no_update,) * 6 + (_error(str(error)),)
        return (
            draft,
            catalog.to_document(),
            catalog.administrator_background_color,
            catalog.administrator_text_color,
            catalog.guest_background_color,
            catalog.guest_text_color,
            None,
        )

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        # Guardar actualiza a la vez el workspace activo y el checkpoint persistente recuperable.
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        State(SOURCE_REVISION_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_users_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        catalog_data: dict[str, object] | None,
        source_revision: str | None,
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
            catalog = _catalog(catalog_data)
            base_revision = _draft_base_source_revision(
                current_draft,
                owner_subject_id=context.draft_owner_provider(),
                fallback=source_revision,
            )
            draft = _browser_draft_document(
                catalog=catalog,
                owner_subject_id=context.draft_owner_provider(),
                base_source_revision=base_revision,
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return draft, draft, None


def _empty_catalog() -> UsersConfigurationCatalog:
    return UsersConfigurationCatalog(
        administrator_background_color=DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
        administrator_text_color=DEFAULT_ADMINISTRATOR_TEXT_COLOR,
        guest_background_color=DEFAULT_GUEST_BACKGROUND_COLOR,
        guest_text_color=DEFAULT_GUEST_TEXT_COLOR,
    )


def _catalog(data: dict[str, object] | None) -> UsersConfigurationCatalog:
    if not isinstance(data, dict):
        return UsersConfigurationCatalog(
            administrator_background_color=DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
            administrator_text_color=DEFAULT_ADMINISTRATOR_TEXT_COLOR,
            guest_background_color=DEFAULT_GUEST_BACKGROUND_COLOR,
            guest_text_color=DEFAULT_GUEST_TEXT_COLOR,
        )
    return UsersConfigurationCatalog.from_document(data)


def _catalog_from_browser_draft(
    data: dict[str, object] | None,
    owner_subject_id: str,
) -> UsersConfigurationCatalog:
    if not isinstance(data, dict) or data.get('schema_version') not in {1, 2}:
        raise ValueError('Browser draft does not exist')
    if str(data.get('owner_subject_id', '')).strip() != owner_subject_id.strip():
        raise ValueError('Browser draft belongs to another user')
    payload = data.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('Browser draft payload is invalid')
    catalog = UsersConfigurationCatalog.from_document(dict(payload))
    revision = build_users_configuration_digest(catalog)
    if str(data.get('revision', '')).strip() != revision:
        raise ValueError('Browser draft revision does not match content')
    return catalog


def _browser_draft_document(
    *,
    catalog: UsersConfigurationCatalog,
    owner_subject_id: str,
    base_source_revision: str | None,
) -> dict[str, object]:
    owner = owner_subject_id.strip()
    if not owner:
        raise ValueError('Browser draft owner is required')
    return {
        'schema_version': _BROWSER_DRAFT_SCHEMA_VERSION,
        'owner_subject_id': owner,
        'revision': build_users_configuration_digest(catalog),
        'saved_at': datetime.now(UTC).isoformat(),
        'base_source_revision': base_source_revision,
        'payload': catalog.to_document(),
    }


def _draft_base_source_revision(
    data: dict[str, object] | None,
    *,
    owner_subject_id: str,
    fallback: str | None,
) -> str | None:
    if not isinstance(data, dict):
        return fallback
    if str(data.get('owner_subject_id', '')).strip() != owner_subject_id.strip():
        return fallback
    value = data.get('base_source_revision')
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _save_profile(
    catalog: UsersConfigurationCatalog,
    editor_data: dict[str, object] | None,
    name: str | None,
    background_color: str | None,
    text_color: str | None,
) -> UsersConfigurationCatalog:
    label = str(name or '').strip()
    mode = str((editor_data or {}).get('mode', 'create'))
    if mode == 'edit':
        key = str((editor_data or {}).get('key', '')).strip()
    else:
        key = build_profile_key(label)
    profile = UserProfileConfiguration(
        key=key,
        label=label,
        background_color=str(background_color or ''),
        text_color=str(text_color or ''),
    )
    if mode == 'edit':
        profiles = tuple(profile if item.key == key else item for item in catalog.profiles)
    else:
        if any(item.key == key for item in catalog.profiles):
            raise ValueError('Profile already exists')
        profiles = (*catalog.profiles, profile)
    return UsersConfigurationCatalog(
        administrator_background_color=catalog.administrator_background_color,
        administrator_text_color=catalog.administrator_text_color,
        guest_background_color=catalog.guest_background_color,
        guest_text_color=catalog.guest_text_color,
        profiles=profiles,
        users=catalog.users,
    )


def _save_user(
    catalog: UsersConfigurationCatalog,
    editor_data: dict[str, object] | None,
    *,
    display_name: str | None,
    email: str | None,
    profile_key: str | None,
    enabled: bool,
    discovered: DiscoveredUser | None = None,
) -> UsersConfigurationCatalog:
    editor = editor_data or {'mode': 'create'}
    mode = str(editor.get('mode', 'create'))
    replace_user_id = _optional_text(editor.get('replace_user_id'))
    existing = None
    if mode == 'edit':
        replace_user_id = str(editor.get('user_id', '')).strip()
    if replace_user_id is not None:
        existing = next(
            (user for user in catalog.users if user.user_id == replace_user_id),
            None,
        )
        if existing is None:
            raise ValueError('User does not exist')

    issuer = _optional_text(editor.get('issuer'))
    subject_id = _optional_text(editor.get('subject_id'))
    user_id = str(editor.get('user_id', '')).strip() or None
    if mode == 'create' and discovered is not None:
        issuer = discovered.issuer
        subject_id = discovered.subject_id
        user_id = discovered.user_id
    user = UserConfiguration.create(
        user_id=user_id,
        issuer=issuer,
        subject_id=subject_id,
        display_name=str(display_name or ''),
        email=str(email or ''),
        profile_key=str(profile_key or ''),
        enabled=enabled,
    )
    if existing is not None:
        users = tuple(user if item.user_id == existing.user_id else item for item in catalog.users)
    else:
        if any(item.user_id == user.user_id for item in catalog.users):
            raise ValueError('User already exists')
        if any(item.email == user.email for item in catalog.users):
            raise ValueError('User email already exists')
        users = (*catalog.users, user)
    return UsersConfigurationCatalog(
        administrator_background_color=catalog.administrator_background_color,
        administrator_text_color=catalog.administrator_text_color,
        guest_background_color=catalog.guest_background_color,
        guest_text_color=catalog.guest_text_color,
        profiles=catalog.profiles,
        users=users,
    )


def _assignable_profile_options(catalog: UsersConfigurationCatalog) -> list[dict[str, str]]:
    return [
        {'label': profile.label, 'value': profile.key}
        for profile in catalog.profile_catalog().assignable()
    ]


def _profile_cards(catalog: UsersConfigurationCatalog) -> object:
    if not catalog.profiles:
        return _empty('Todavía no hay perfiles personalizados.')
    used = {user.profile_key for user in catalog.users}
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
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
                            html.Code(profile.key),
                        ],
                        className='atlanticus-users-admin__profile-copy',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Editar',
                                id=profile_edit_id(profile.key),
                                n_clicks=0,
                                className='atlanticus-users-admin__action',
                            ),
                            html.Button(
                                'Eliminar',
                                id=profile_delete_id(profile.key),
                                n_clicks=0,
                                disabled=profile.key in used,
                                title=(
                                    'El perfil está asignado a usuarios'
                                    if profile.key in used
                                    else 'Eliminar perfil del borrador'
                                ),
                                className=(
                                    'atlanticus-users-admin__action '
                                    'atlanticus-users-admin__action--danger'
                                ),
                            ),
                        ],
                        className='atlanticus-users-admin__card-actions',
                    ),
                ],
                className='atlanticus-users-admin__list-card',
            )
            for profile in catalog.profiles
        ],
        className='atlanticus-users-admin__list',
    )


def _user_cards(catalog: UsersConfigurationCatalog) -> object:
    if not catalog.users:
        return _empty('Todavía no hay usuarios configurados.')
    profiles = catalog.profile_catalog()
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(user.display_name),
                            html.Span(user.email),
                            html.Code(user.user_id),
                        ],
                        className='atlanticus-users-admin__user-copy',
                    ),
                    html.Div(
                        [
                            _profile_badge(profiles.require(user.profile_key)),
                            html.Span(
                                'Activo' if user.enabled else 'Deshabilitado',
                                className=(
                                    'atlanticus-users-admin__status '
                                    + (
                                        'atlanticus-users-admin__status--enabled'
                                        if user.enabled
                                        else 'atlanticus-users-admin__status--disabled'
                                    )
                                ),
                            ),
                            html.Button(
                                'Editar',
                                id=user_edit_id(user.user_id),
                                n_clicks=0,
                                className='atlanticus-users-admin__action',
                            ),
                        ],
                        className='atlanticus-users-admin__card-actions',
                    ),
                ],
                className='atlanticus-users-admin__list-card',
            )
            for user in catalog.users
        ],
        className='atlanticus-users-admin__list',
    )


def _discovered_cards(
    users: tuple[DiscoveredUser, ...],
    catalog: UsersConfigurationCatalog,
) -> object:
    if not users:
        return _empty('No hay usuarios Guest pendientes de incorporar.')
    configured_by_email = {user.email: user for user in catalog.users}
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(user.display_name),
                            html.Span(user.email),
                            html.Code(user.user_id),
                        ],
                        className='atlanticus-users-admin__user-copy',
                    ),
                    html.Div(
                        [
                            html.Span(
                                (
                                    'Identidad detectada'
                                    if user.email in configured_by_email
                                    else 'Guest'
                                ),
                                className='atlanticus-users-admin__status',
                            ),
                            html.Button(
                                (
                                    'Vincular identidad'
                                    if user.email in configured_by_email
                                    else 'Incorporar'
                                ),
                                id=discovered_add_id(user.user_id),
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
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


def _profile_badge(profile: ProfileDefinition) -> object:
    return html.Span(
        profile.label,
        className='atlanticus-users-admin__profile-badge',
        style={
            'backgroundColor': profile.background_color,
            'color': profile.text_color,
        },
    )


def _find_discovered(context: UsersAdminWebContext, user_id: str) -> DiscoveredUser | None:
    try:
        return next(
            (
                item
                for item in context.services.administration.list_discovered()
                if item.user_id == user_id
            ),
            None,
        )
    except Exception:
        return None


def _find_discovered_by_email(
    context: UsersAdminWebContext,
    email: str,
) -> DiscoveredUser | None:
    normalized = email.strip().casefold()
    if not normalized:
        return None
    try:
        matches = tuple(
            item
            for item in context.services.administration.list_discovered()
            if item.email == normalized
        )
    except Exception:
        return None
    if len(matches) > 1:
        raise ValueError('Multiple discovered identities use the same email')
    return matches[0] if matches else None


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
    if mode == 'discovered':
        return (
            'Vincular identidad descubierta'
            if (editor_data or {}).get('replace_user_id')
            else 'Incorporar usuario descubierto'
        )
    if mode == 'edit':
        return 'Editar usuario'
    return 'Nuevo usuario'


def _user_identity_locked(editor_data: dict[str, object] | None) -> bool:
    return str((editor_data or {}).get('mode', '')) == 'discovered'


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
    catalog: dict[str, object] | None = None,
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
            catalog or no_update,
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
        catalog if catalog is not None else no_update,
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
    catalog: dict[str, object] | None = None,
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
            ['enabled'],
            False,
            False,
            None,
            catalog or no_update,
        )
    return (
        _MODAL_OPEN,
        editor,
        title or 'Usuario',
        name or '',
        email or '',
        options or [],
        profile,
        ['enabled'] if enabled else [],
        identity_locked,
        identity_locked,
        _error(error) if error else None,
        catalog if catalog is not None else no_update,
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


def _register_native_color_picker(app: object, picker_id: str) -> None:
    button_id = color_picker_button_id(picker_id)
    swatch_id = color_picker_swatch_id(picker_id)
    script = f"""
    function(nClicks, currentColor) {{
        if (!nClicks) {{
            return dash_clientside.no_update;
        }}
        const picker = document.createElement('input');
        picker.type = 'color';
        picker.value = currentColor || '#000000';
        picker.style.position = 'fixed';
        picker.style.left = '-9999px';
        picker.addEventListener('input', function(event) {{
            const color = event.target.value;
            dash_clientside.set_props('{picker_id}', {{value: color}});
            dash_clientside.set_props('{swatch_id}', {{style: {{backgroundColor: color}}}});
        }});
        picker.addEventListener('change', function() {{
            picker.remove();
        }}, {{once: true}});
        document.body.appendChild(picker);
        picker.click();
        return dash_clientside.no_update;
    }}
    """
    app.clientside_callback(
        script,
        Output(button_id, 'title'),
        Input(button_id, 'n_clicks'),
        State(picker_id, 'value'),
        prevent_initial_call=True,
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


def _matches_trigger(trigger: object, *ids: str) -> bool:
    return isinstance(trigger, str) and trigger in ids


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _empty(message: str) -> object:
    return html.Div(message, className='atlanticus-users-admin__empty')


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-users-admin__message atlanticus-users-admin__message--error',
    )
