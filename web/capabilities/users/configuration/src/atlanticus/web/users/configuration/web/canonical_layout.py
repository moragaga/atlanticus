from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.configuration import (
    UsersProfilesConfiguration,
    default_users_profiles_configuration,
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
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SECTION_STORE_ID,
    SOURCE_NAME_ID,
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
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext

_MODAL_CLOSED = 'atlanticus-users-admin__modal'


def build_users_admin_configuration(context: UsersAdminWebContext) -> object:
    configuration = default_users_profiles_configuration()
    administrator = _administrator(configuration)
    return html.Div(
        [
            dcc.Store(
                id=CATALOG_STORE_ID,
                data=configuration.to_document(),
                storage_type='memory',
            ),
            dcc.Store(id=DRAFT_BASIS_STORE_ID, data=None, storage_type='memory'),
            dcc.Store(id=SECTION_STORE_ID, data='profiles', storage_type='memory'),
            dcc.Store(id=PROFILE_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=USER_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            html.Div(id=DRAFT_RECOVERY_RESULT_ID),
            _editor_navigation(),
            html.Div(
                _profiles_panel(administrator),
                id=PROFILE_PANEL_ID,
                className='atlanticus-users-admin__panel atlanticus-users-admin__panel--active',
            ),
            html.Div(
                _users_panel(),
                id=USERS_PANEL_ID,
                className='atlanticus-users-admin__panel',
            ),
            html.Div(
                _discovered_panel(),
                id=DISCOVERED_PANEL_ID,
                className='atlanticus-users-admin__panel',
            ),
            _save_section(),
            _profile_modal(),
            _user_modal(),
        ],
        className='atlanticus-users-admin atlanticus-bootstrap',
    )


def _administrator(configuration: UsersProfilesConfiguration) -> ProfileDefinition:
    return configuration.profile_catalog().require('administrator')


def _runtime_context(context: UsersAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [html.Span('Fuente de verdad'), html.Strong(context.source_name, id=SOURCE_NAME_ID)],
                className='atlanticus-users-admin__runtime-source',
            ),
            html.Div(
                [html.Span('Proyección'), html.Strong(context.projection_name, id=PROJECTION_NAME_ID)],
                className='atlanticus-users-admin__runtime-source',
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=dbc.Button('Importar', color='secondary', outline=True),
                        multiple=False,
                    ),
                    html.Span(
                        'Incluye perfiles y usuarios. Se carga como cambios locales y no modifica la fuente.',
                        className='atlanticus-users-admin__runtime-help',
                    ),
                    html.Div(id=IMPORT_RESULT_ID),
                ],
                className='atlanticus-users-admin__import',
            ),
        ],
        className='atlanticus-users-admin__runtime-context',
    )


def _editor_navigation() -> object:
    return html.Nav(
        [
            html.Button(
                'Perfiles',
                id=PROFILE_TAB_ID,
                n_clicks=0,
                className='nav-link active atlanticus-users-admin__tab',
            ),
            html.Button(
                'Usuarios',
                id=USERS_TAB_ID,
                n_clicks=0,
                className='nav-link atlanticus-users-admin__tab',
            ),
            html.Button(
                'Pendientes',
                id=DISCOVERED_TAB_ID,
                n_clicks=0,
                className='nav-link atlanticus-users-admin__tab',
            ),
        ],
        className='nav nav-tabs atlanticus-users-admin__tabs',
    )


def _profiles_panel(administrator: ProfileDefinition) -> object:
    return html.Div(
        [
            html.Section(
                [
                    _section_heading(
                        'Perfil Administrator',
                        (
                            'Administrator es un perfil funcional asignable a usuarios gestionados. '
                            'Su definición vive en ProfilesConfiguration.'
                        ),
                    ),
                    html.Div(
                        [
                            _configured_profile_card(
                                title='Administrator',
                                description='Perfil funcional base administrado por Users + Profiles.',
                                background_color=administrator.background_color,
                                text_color=administrator.text_color,
                            )
                        ],
                        className='atlanticus-users-admin__system-grid',
                    ),
                ],
                className='atlanticus-users-admin__section',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            _section_heading(
                                'Perfiles funcionales',
                                'Define perfiles reutilizables con identidad estable.',
                            ),
                            dbc.Button(
                                '+ Perfil',
                                id=ADD_PROFILE_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                        ],
                        className='atlanticus-users-admin__section-heading-row',
                    ),
                    html.Div(id=PROFILES_LIST_ID),
                ],
                className='atlanticus-users-admin__section',
            ),
        ],
        className='atlanticus-users-admin__panel-content',
    )


def _users_panel() -> object:
    return html.Section(
        [
            _section_heading(
                'Usuarios configurados',
                'Los usuarios se incorporan desde Pendientes y siempre resuelven un perfil funcional.',
            ),
            html.Div(id=USERS_LIST_ID),
        ],
        className='atlanticus-users-admin__section',
    )


def _discovered_panel() -> object:
    return html.Section(
        [
            html.Div(
                [
                    _section_heading(
                        'Identidades pendientes de incorporación',
                        'Identidades detectadas que todavía no forman parte de la configuración.',
                    ),
                    dbc.Button(
                        'Actualizar',
                        id=DISCOVERED_REFRESH_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                    ),
                ],
                className='atlanticus-users-admin__section-heading-row',
            ),
            html.Div(id=DISCOVERED_LIST_ID),
        ],
        className='atlanticus-users-admin__section',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · perfiles y usuarios'),
                            html.P(
                                'Guarda UsersProfilesAdminDraft schema 2 con su SourceSnapshot exacto.'
                            ),
                        ],
                        className='atlanticus-users-admin__section-heading-copy',
                    ),
                    dbc.Button(
                        'Guardar borrador',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        color='primary',
                    ),
                ],
                className='atlanticus-users-admin__section-heading-row',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className='atlanticus-users-admin__section atlanticus-users-admin__section--footer',
    )


def _configured_profile_card(
    *,
    title: str,
    description: str,
    background_color: str,
    text_color: str,
) -> object:
    return html.Article(
        [
            html.Div(
                [
                    _profile_preview(
                        preview_id=ADMINISTRATOR_PREVIEW_ID,
                        label=title,
                        background_color=background_color,
                        text_color=text_color,
                    ),
                    html.P(description),
                ],
                className='atlanticus-users-admin__profile-copy',
            ),
            html.Div(
                [
                    _color_picker(
                        label='Fondo',
                        picker_id=ADMINISTRATOR_BACKGROUND_COLOR_ID,
                        value=background_color,
                    ),
                    _color_picker(
                        label='Texto',
                        picker_id=ADMINISTRATOR_TEXT_COLOR_ID,
                        value=text_color,
                    ),
                ],
                className='atlanticus-users-admin__color-pickers',
            ),
        ],
        className='atlanticus-users-admin__profile-card',
    )


def _profile_modal() -> object:
    return html.Div(
        [
            html.Button(
                id=PROFILE_CANCEL_ID,
                className='atlanticus-users-admin__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Section(
                [
                    _modal_header(PROFILE_MODAL_TITLE_ID, PROFILE_CANCEL_ID + '-header'),
                    html.Div(
                        [
                            _field(
                                'Nombre',
                                dbc.Input(
                                    id=PROFILE_NAME_ID,
                                    type='text',
                                    placeholder='Ej. Operador Planta',
                                    autoComplete='off',
                                ),
                            ),
                            _reference_field('Identificador', PROFILE_KEY_ID),
                            html.Div(
                                [
                                    _color_picker(
                                        label='Color de fondo',
                                        picker_id=PROFILE_BACKGROUND_COLOR_ID,
                                        value='#C9A24B',
                                    ),
                                    _color_picker(
                                        label='Color del texto',
                                        picker_id=PROFILE_TEXT_COLOR_ID,
                                        value='#071522',
                                    ),
                                ],
                                className='atlanticus-users-admin__color-pickers',
                            ),
                            _profile_preview(
                                preview_id=PROFILE_PREVIEW_ID,
                                label='Perfil',
                                background_color='#C9A24B',
                                text_color='#071522',
                            ),
                            html.Div(id=PROFILE_RESULT_ID),
                        ],
                        className='modal-body atlanticus-users-admin__modal-body',
                    ),
                    _modal_footer(PROFILE_SAVE_ID, PROFILE_CANCEL_ID + '-footer'),
                ],
                className='modal-content atlanticus-users-admin__modal-dialog',
            ),
        ],
        id=PROFILE_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _user_modal() -> object:
    return html.Div(
        [
            html.Button(
                id=USER_CANCEL_ID,
                className='atlanticus-users-admin__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Section(
                [
                    _modal_header(USER_MODAL_TITLE_ID, USER_CANCEL_ID + '-header'),
                    html.Div(
                        [
                            _field('Nombre', dbc.Input(id=USER_NAME_ID, type='text')),
                            _field('Correo', dbc.Input(id=USER_EMAIL_ID, type='email')),
                            _field(
                                'Perfil',
                                dcc.Dropdown(id=USER_PROFILE_ID, clearable=False),
                            ),
                            dbc.Checkbox(id=USER_ENABLED_ID, value=True, label='Habilitado'),
                            html.Div(id=USER_RESULT_ID),
                        ],
                        className='modal-body atlanticus-users-admin__modal-body',
                    ),
                    _modal_footer(USER_SAVE_ID, USER_CANCEL_ID + '-footer'),
                ],
                className='modal-content atlanticus-users-admin__modal-dialog',
            ),
        ],
        id=USER_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _modal_header(title_id: str, close_id: str) -> object:
    return html.Div(
        [
            html.H3(id=title_id),
            html.Button('×', id=close_id, n_clicks=0, className='btn-close'),
        ],
        className='modal-header',
    )


def _modal_footer(save_id: str, cancel_id: str) -> object:
    return html.Div(
        [
            dbc.Button('Cancelar', id=cancel_id, n_clicks=0, color='secondary', outline=True),
            dbc.Button('Guardar', id=save_id, n_clicks=0, color='primary'),
        ],
        className='modal-footer',
    )


def _section_heading(title: str, description: str) -> object:
    return html.Div(
        [html.H3(title), html.P(description)],
        className='atlanticus-users-admin__section-heading-copy',
    )


def _field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label, className='atlanticus-users-admin__field-label'), control],
        className='atlanticus-users-admin__field',
    )


def _reference_field(label: str, value_id: str) -> object:
    return html.Div(
        [
            html.Span(label, className='atlanticus-users-admin__field-label'),
            html.Code(id=value_id),
        ],
        className='atlanticus-users-admin__field',
    )


def _color_picker(*, label: str, picker_id: str, value: str) -> object:
    return html.Label(
        [
            html.Span(label, className='atlanticus-users-admin__field-label'),
            dcc.Input(id=picker_id, type='color', value=value),
        ],
        className='atlanticus-users-admin__field',
    )


def _profile_preview(
    *,
    preview_id: str,
    label: str,
    background_color: str,
    text_color: str,
) -> object:
    return html.Div(
        [
            html.Span(label[:1].upper(), className='atlanticus-users-admin__profile-avatar'),
            html.Strong(label),
        ],
        id=preview_id,
        className='atlanticus-users-admin__profile-preview',
        style={
            '--atlanticus-users-profile-background-color': background_color,
            '--atlanticus-users-profile-text-color': text_color,
        },
    )
