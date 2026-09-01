from __future__ import annotations

from dash import dcc, html

from atlanticus.web.users.configuration.models import UsersConfigurationCatalog
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
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SECTION_STORE_ID,
    SOURCE_NAME_ID,
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
)
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext
from atlanticus.web.users.profiles import (
    DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
    DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    DEFAULT_GUEST_BACKGROUND_COLOR,
    DEFAULT_GUEST_TEXT_COLOR,
    LOCAL_JANE_BACKGROUND_COLOR,
    LOCAL_JANE_TEXT_COLOR,
    LOCAL_JOHN_BACKGROUND_COLOR,
    LOCAL_JOHN_TEXT_COLOR,
)

_MODAL_CLOSED = 'atlanticus-users-admin__modal'


def build_users_admin_configuration(context: UsersAdminWebContext) -> object:
    catalog = _empty_catalog()
    return html.Div(
        [
            dcc.Store(
                id=CATALOG_STORE_ID,
                data=catalog.to_document(),
                storage_type='memory',
            ),
            dcc.Store(
                id=SOURCE_REVISION_STORE_ID,
                data=None,
                storage_type='memory',
            ),
            dcc.Store(id=SECTION_STORE_ID, data='profiles', storage_type='memory'),
            dcc.Store(id=PROFILE_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=USER_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            _editor_navigation(),
            html.Div(
                _profiles_panel(catalog),
                id=PROFILE_PANEL_ID,
                className='atlanticus-users-admin__panel atlanticus-users-admin__panel--active',
            ),
            html.Div(
                _users_panel(catalog),
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
        className='atlanticus-users-admin',
    )


def _empty_catalog() -> UsersConfigurationCatalog:
    return UsersConfigurationCatalog(
        administrator_background_color=DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
        administrator_text_color=DEFAULT_ADMINISTRATOR_TEXT_COLOR,
        guest_background_color=DEFAULT_GUEST_BACKGROUND_COLOR,
        guest_text_color=DEFAULT_GUEST_TEXT_COLOR,
    )


def _runtime_context(context: UsersAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ],
                className='atlanticus-users-admin__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ],
                className='atlanticus-users-admin__runtime-source',
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=html.Button(
                            'Importar archivo de Users',
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--secondary'
                            ),
                        ),
                        multiple=False,
                    ),
                    html.Span(
                        (
                            'Incluye perfiles y usuarios. Se carga como borrador local '
                            'y no modifica la fuente.'
                        ),
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
                className=('atlanticus-users-admin__tab atlanticus-users-admin__tab--active'),
            ),
            html.Button(
                'Usuarios',
                id=USERS_TAB_ID,
                n_clicks=0,
                className='atlanticus-users-admin__tab',
            ),
            html.Button(
                'Descubiertos',
                id=DISCOVERED_TAB_ID,
                n_clicks=0,
                className='atlanticus-users-admin__tab',
            ),
        ],
        className='atlanticus-users-admin__tabs',
    )


def _profiles_panel(catalog: UsersConfigurationCatalog) -> object:
    return html.Div(
        [
            html.Section(
                [
                    _section_heading(
                        'Perfiles del sistema',
                        (
                            'Local conserva identidades visuales fijas. Administrator y Guest '
                            'permiten configurar los colores de fondo y texto.'
                        ),
                    ),
                    html.Div(
                        [
                            _local_profile_card(),
                            _system_profile_card(
                                title='Administrator',
                                key='administrator',
                                description='Acceso total. No requiere asignaciones de Navigation.',
                                background_color=catalog.administrator_background_color,
                                text_color=catalog.administrator_text_color,
                                background_color_id=ADMINISTRATOR_BACKGROUND_COLOR_ID,
                                text_color_id=ADMINISTRATOR_TEXT_COLOR_ID,
                                preview_id=ADMINISTRATOR_PREVIEW_ID,
                            ),
                            _system_profile_card(
                                title='Guest',
                                key='guest',
                                description='Acceso definido posteriormente por Navigation.',
                                background_color=catalog.guest_background_color,
                                text_color=catalog.guest_text_color,
                                background_color_id=GUEST_BACKGROUND_COLOR_ID,
                                text_color_id=GUEST_TEXT_COLOR_ID,
                                preview_id=GUEST_PREVIEW_ID,
                            ),
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
                                'Perfiles personalizados',
                                (
                                    'Define perfiles reutilizables. El identificador se genera '
                                    'automáticamente y permanece estable.'
                                ),
                            ),
                            html.Button(
                                '+ Perfil',
                                id=ADD_PROFILE_ID,
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
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


def _users_panel(catalog: UsersConfigurationCatalog) -> object:
    del catalog
    return html.Section(
        [
            html.Div(
                [
                    _section_heading(
                        'Usuarios configurados',
                        (
                            'Asigna un único perfil efectivo y controla si el usuario puede '
                            'acceder. Las páginas se definirán en Navigation.'
                        ),
                    ),
                    html.Button(
                        '+ Usuario',
                        id=ADD_USER_ID,
                        n_clicks=0,
                        className=(
                            'atlanticus-manager__button atlanticus-manager__button--secondary'
                        ),
                    ),
                ],
                className='atlanticus-users-admin__section-heading-row',
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
                        'Usuarios descubiertos',
                        (
                            'Identidades válidas detectadas por Atlanticus que todavía operan '
                            'como Guest y no forman parte de la configuración publicada.'
                        ),
                    ),
                    html.Button(
                        'Actualizar',
                        id=DISCOVERED_REFRESH_ID,
                        n_clicks=0,
                        className=(
                            'atlanticus-manager__button atlanticus-manager__button--secondary'
                        ),
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
                            html.H3('Borrador de Users · perfiles y usuarios'),
                            html.P(
                                (
                                    'Guarda perfiles y usuarios en este navegador. Validar, '
                                    'publicar y proyectar se realiza en Estado y trazabilidad.'
                                )
                            ),
                        ],
                        className='atlanticus-users-admin__section-heading-copy',
                    ),
                    html.Button(
                        'Guardar borrador de Users',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        className=(
                            'atlanticus-manager__button atlanticus-manager__button--primary'
                        ),
                    ),
                ],
                className='atlanticus-users-admin__section-heading-row',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className=('atlanticus-users-admin__section atlanticus-users-admin__section--footer'),
    )


def _local_profile_card() -> object:
    return html.Article(
        [
            html.Div(
                [
                    html.Strong('Local'),
                    html.Code('local'),
                    html.P('Controlado por Atlanticus. Acceso total en modo local.'),
                ],
                className='atlanticus-users-admin__profile-copy',
            ),
            html.Div(
                [
                    _fixed_persona(
                        'John Doe',
                        LOCAL_JOHN_BACKGROUND_COLOR,
                        LOCAL_JOHN_TEXT_COLOR,
                    ),
                    _fixed_persona(
                        'Jane Doe',
                        LOCAL_JANE_BACKGROUND_COLOR,
                        LOCAL_JANE_TEXT_COLOR,
                    ),
                ],
                className='atlanticus-users-admin__local-personas',
            ),
        ],
        className='atlanticus-users-admin__profile-card',
    )


def _fixed_persona(label: str, background_color: str, text_color: str) -> object:
    return html.Div(
        [
            html.Span(
                label[:1].upper(),
                style={
                    'backgroundColor': background_color,
                    'color': text_color,
                },
                className='atlanticus-users-admin__persona-swatch',
            ),
            html.Strong(label),
        ],
        className='atlanticus-users-admin__persona',
    )


def _system_profile_card(
    *,
    title: str,
    key: str,
    description: str,
    background_color: str,
    text_color: str,
    background_color_id: str,
    text_color_id: str,
    preview_id: str,
) -> object:
    return html.Article(
        [
            html.Div(
                [
                    _profile_preview(
                        preview_id=preview_id,
                        label=title,
                        background_color=background_color,
                        text_color=text_color,
                    ),
                    html.Code(key),
                    html.P(description),
                ],
                className='atlanticus-users-admin__profile-copy',
            ),
            html.Div(
                [
                    _color_picker(
                        label='Fondo',
                        picker_id=background_color_id,
                        value=background_color,
                    ),
                    _color_picker(
                        label='Texto',
                        picker_id=text_color_id,
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
                    _modal_header('Perfil', PROFILE_MODAL_TITLE_ID, PROFILE_CANCEL_ID + '-header'),
                    html.Div(
                        [
                            _field(
                                'Nombre',
                                dcc.Input(
                                    id=PROFILE_NAME_ID,
                                    type='text',
                                    placeholder='Ej. Operador Planta',
                                    autoComplete='off',
                                ),
                                'El identificador se genera una sola vez al crear el perfil.',
                            ),
                            _reference_field(
                                'Identificador',
                                PROFILE_KEY_ID,
                                'Se usa internamente por Users y Navigation.',
                            ),
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
                            html.Div(
                                [
                                    html.Span(
                                        'Vista previa',
                                        className='atlanticus-users-admin__field-label',
                                    ),
                                    _profile_preview(
                                        preview_id=PROFILE_PREVIEW_ID,
                                        label='Perfil',
                                        background_color='#C9A24B',
                                        text_color='#071522',
                                    ),
                                ],
                                className='atlanticus-users-admin__profile-preview-field',
                            ),
                            html.Div(id=PROFILE_RESULT_ID),
                        ],
                        className='atlanticus-users-admin__modal-body',
                    ),
                    _modal_actions(
                        cancel_id=PROFILE_CANCEL_ID + '-footer',
                        save_id=PROFILE_SAVE_ID,
                        save_label='Guardar perfil',
                    ),
                ],
                className='atlanticus-users-admin__modal-dialog',
            ),
        ],
        id=PROFILE_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _color_picker(*, label: str, picker_id: str, value: str) -> object:
    return html.Div(
        [
            html.Span(label, className='atlanticus-users-admin__field-label'),
            dcc.Input(
                id=picker_id,
                type='text',
                value=value,
                style={'display': 'none'},
            ),
            html.Button(
                [
                    html.Span(
                        id=color_picker_swatch_id(picker_id),
                        className='atlanticus-users-admin__color-picker-swatch',
                        style={'backgroundColor': value},
                    ),
                    html.Span('Seleccionar'),
                ],
                id=color_picker_button_id(picker_id),
                n_clicks=0,
                type='button',
                title=f'Seleccionar {label.lower()}',
                className='atlanticus-users-admin__color-picker',
            ),
        ],
        className='atlanticus-users-admin__color-picker-field',
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
            html.Span(
                label[:1].upper(),
                className='atlanticus-users-admin__profile-avatar',
            ),
            html.Strong(label),
        ],
        id=preview_id,
        className='atlanticus-users-admin__profile-preview',
        style={
            '--atlanticus-users-profile-background-color': background_color,
            '--atlanticus-users-profile-text-color': text_color,
        },
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
                    _modal_header('Usuario', USER_MODAL_TITLE_ID, USER_CANCEL_ID + '-header'),
                    html.Div(
                        [
                            _field(
                                'Nombre',
                                dcc.Input(
                                    id=USER_NAME_ID,
                                    type='text',
                                    placeholder='Nombre visible',
                                    autoComplete='off',
                                ),
                                'Para usuarios descubiertos se conserva la identidad de Entra.',
                            ),
                            _field(
                                'Correo',
                                dcc.Input(
                                    id=USER_EMAIL_ID,
                                    type='email',
                                    placeholder='usuario@empresa.cl',
                                    autoComplete='off',
                                ),
                                'Puede preprovisionarse antes de que el usuario ingrese.',
                            ),
                            _field(
                                'Perfil',
                                dcc.Dropdown(
                                    id=USER_PROFILE_ID,
                                    clearable=False,
                                    searchable=False,
                                    placeholder='Selecciona un perfil',
                                ),
                                'Administrator o uno de los perfiles personalizados.',
                            ),
                            html.Label(
                                [
                                    dcc.Checklist(
                                        id=USER_ENABLED_ID,
                                        options=[
                                            {
                                                'label': ' Usuario habilitado',
                                                'value': 'enabled',
                                            }
                                        ],
                                        value=['enabled'],
                                    )
                                ],
                                className='atlanticus-users-admin__enabled-field',
                            ),
                            html.Div(id=USER_RESULT_ID),
                        ],
                        className='atlanticus-users-admin__modal-body',
                    ),
                    _modal_actions(
                        cancel_id=USER_CANCEL_ID + '-footer',
                        save_id=USER_SAVE_ID,
                        save_label='Guardar usuario',
                    ),
                ],
                className='atlanticus-users-admin__modal-dialog',
            ),
        ],
        id=USER_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _modal_header(eyebrow: str, title_id: str, close_id: str) -> object:
    return html.Header(
        [
            html.Div(
                [
                    html.P(eyebrow, className='atlanticus-users-admin__modal-eyebrow'),
                    html.H3(id=title_id),
                ]
            ),
            html.Button(
                '×',
                id=close_id,
                n_clicks=0,
                className='atlanticus-manager__icon-button',
                title='Cerrar',
            ),
        ],
        className='atlanticus-users-admin__modal-header',
    )


def _modal_actions(*, cancel_id: str, save_id: str, save_label: str) -> object:
    return html.Footer(
        [
            html.Button(
                'Cancelar',
                id=cancel_id,
                n_clicks=0,
                className=('atlanticus-manager__button atlanticus-manager__button--secondary'),
            ),
            html.Button(
                save_label,
                id=save_id,
                n_clicks=0,
                className='atlanticus-manager__button atlanticus-manager__button--primary',
            ),
        ],
        className='atlanticus-users-admin__modal-actions',
    )


def _section_heading(title: str, description: str) -> object:
    return html.Div(
        [html.H3(title), html.P(description)],
        className='atlanticus-users-admin__section-heading-copy',
    )


def _field(label: str, control: object, help_text: str) -> object:
    return html.Label(
        [
            html.Span(label, className='atlanticus-users-admin__field-label'),
            control,
            html.Small(help_text),
        ],
        className='atlanticus-users-admin__field',
    )


def _reference_field(label: str, value_id: str, help_text: str) -> object:
    return html.Div(
        [
            html.Span(label, className='atlanticus-users-admin__field-label'),
            html.Code('Se genera al guardar', id=value_id),
            html.Small(help_text),
        ],
        className='atlanticus-users-admin__field atlanticus-users-admin__field--reference',
    )
