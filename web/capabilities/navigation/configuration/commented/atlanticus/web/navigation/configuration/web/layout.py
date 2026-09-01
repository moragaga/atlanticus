# Construye Navigation desde un catálogo local vacío cuando no existe draft y renderiza esa estructura desde el primer montaje.
# La acción de archivo se etiqueta como importación para no confundirla con cargar Source desde Manager.

from __future__ import annotations

from dash import dcc, html

from atlanticus.web.navigation.configuration.editor import build_initial_catalog
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.profiles import resolve_profile_options
from atlanticus.web.navigation.configuration.web.ids import (
    ADD_GROUP_ID,
    ADD_ROOT_LINK_ID,
    CATALOG_STORE_ID,
    GROUP_CANCEL_ID,
    GROUP_EDITOR_STORE_ID,
    GROUP_ENABLED_ID,
    GROUP_ICON_ID,
    GROUP_KEY_ID,
    GROUP_MODAL_ID,
    GROUP_MODAL_TITLE_ID,
    GROUP_NAME_ID,
    GROUP_RESULT_ID,
    GROUP_SAVE_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    LINK_CANCEL_ID,
    LINK_EDITOR_STORE_ID,
    LINK_ENABLED_ID,
    LINK_FORCE_RELOAD_ID,
    LINK_HREF_ID,
    LINK_ICON_ID,
    LINK_KEY_ID,
    LINK_MODAL_ID,
    LINK_MODAL_TITLE_ID,
    LINK_NAME_ID,
    LINK_NEW_TAB_ID,
    LINK_PROFILES_ID,
    LINK_RESULT_ID,
    LINK_SAVE_ID,
    LINK_SECTION_ID,
    MOUNT_STORE_ID,
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
    SOURCE_REVISION_STORE_ID,
    STRUCTURE_ID,
)
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext
from atlanticus.web.navigation.configuration.web.rendering import navigation_structure

_MODAL_CLOSED = 'atlanticus-navigation-admin__modal'


def build_navigation_admin_configuration(context: NavigationAdminWebContext) -> object:
    catalog = build_initial_catalog()
    return html.Div(
        [
            dcc.Store(id=CATALOG_STORE_ID, data=catalog.to_document(), storage_type='memory'),
            dcc.Store(
                id=SOURCE_REVISION_STORE_ID,
                data=None,
                storage_type='memory',
            ),
            dcc.Store(id=LINK_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=GROUP_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            _profiles_context(context),
            _structure_section(catalog),
            _save_section(),
            _link_modal(),
            _group_modal(),
        ],
        className='atlanticus-navigation-admin',
    )


def _runtime_context(context: NavigationAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ],
                className='atlanticus-navigation-admin__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ],
                className='atlanticus-navigation-admin__runtime-source',
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=html.Button(
                            'Importar archivo de Navigation',
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--secondary'
                            ),
                        ),
                        multiple=False,
                    ),
                    html.Span(
                        'Carga rutas, secciones y permisos como borrador local.',
                        className='atlanticus-navigation-admin__runtime-help',
                    ),
                    html.Div(id=IMPORT_RESULT_ID),
                ],
                className='atlanticus-navigation-admin__import',
            ),
        ],
        className='atlanticus-navigation-admin__runtime-context',
    )


def _profiles_context(context: NavigationAdminWebContext) -> object:
    provider = context.profile_options_provider
    try:
        external = provider() if provider is not None else ()
    except Exception:
        external = ()
    profiles = resolve_profile_options(external)
    return html.Section(
        [
            html.Div(
                [
                    html.H3('Perfiles de acceso'),
                    html.P(
                        'Local y Administrador tienen acceso total. Guest y los perfiles '
                        'adicionales se asignan directamente a cada enlace.'
                    ),
                ],
                className='atlanticus-navigation-admin__section-copy',
            ),
            html.Div(
                [_profile_badge(profile) for profile in profiles],
                className='atlanticus-navigation-admin__profiles',
            ),
        ],
        className='atlanticus-navigation-admin__section',
    )


def _profile_badge(profile) -> object:
    classes = 'atlanticus-navigation-admin__profile'
    if profile.unrestricted:
        classes += ' atlanticus-navigation-admin__profile--unrestricted'
    style = {}
    if profile.background_color:
        style['backgroundColor'] = profile.background_color
    if profile.text_color:
        style['color'] = profile.text_color
    return html.Span(profile.label, className=classes, style=style)


def _structure_section(catalog: NavigationConfigurationCatalog) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Estructura de navegación'),
                            html.P(
                                'Los enlaces pueden quedar en la raíz o pertenecer a una sección. '
                                'El orden mostrado es el orden de navegación.'
                            ),
                        ],
                        className='atlanticus-navigation-admin__section-copy',
                    ),
                    html.Div(
                        [
                            html.Button(
                                '+ Enlace',
                                id=ADD_ROOT_LINK_ID,
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                            ),
                            html.Button(
                                '+ Sección',
                                id=ADD_GROUP_ID,
                                n_clicks=0,
                                className=(
                                    'atlanticus-manager__button '
                                    'atlanticus-manager__button--secondary'
                                ),
                            ),
                        ],
                        className='atlanticus-navigation-admin__heading-actions',
                    ),
                ],
                className='atlanticus-navigation-admin__section-heading',
            ),
            html.Div(navigation_structure(catalog), id=STRUCTURE_ID),
        ],
        className='atlanticus-navigation-admin__section',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador de Navigation'),
                            html.P(
                                'Guarda la estructura, rutas y permisos de Navigation '
                                'en este navegador.'
                            ),
                        ],
                        className='atlanticus-navigation-admin__section-copy',
                    ),
                    html.Button(
                        'Guardar borrador de Navigation',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        className=(
                            'atlanticus-manager__button atlanticus-manager__button--primary'
                        ),
                    ),
                ],
                className='atlanticus-navigation-admin__section-heading',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className=(
            'atlanticus-navigation-admin__section atlanticus-navigation-admin__section--footer'
        ),
    )


def _link_modal() -> object:
    return html.Div(
        html.Div(
            [
                html.H3(id=LINK_MODAL_TITLE_ID),
                html.Div(
                    [
                        _field('Nombre', dcc.Input(id=LINK_NAME_ID, type='text')),
                        _field(
                            'Key',
                            dcc.Input(
                                id=LINK_KEY_ID,
                                type='text',
                                disabled=True,
                                placeholder='Se genera al guardar',
                            ),
                        ),
                        _field('Ruta o URL', dcc.Input(id=LINK_HREF_ID, type='text')),
                        _field(
                            'Ícono',
                            dcc.Input(
                                id=LINK_ICON_ID,
                                type='text',
                                placeholder='bi bi-house',
                            ),
                        ),
                        _field(
                            'Sección',
                            dcc.Dropdown(
                                id=LINK_SECTION_ID,
                                clearable=False,
                            ),
                        ),
                        _field(
                            'Perfiles con acceso',
                            dcc.Dropdown(
                                id=LINK_PROFILES_ID,
                                multi=True,
                                placeholder='Seleccionar perfiles',
                            ),
                        ),
                    ],
                    className='atlanticus-navigation-admin__form-grid',
                ),
                html.Div(
                    [
                        _check(LINK_ENABLED_ID, 'Habilitado', 'enabled'),
                        _check(LINK_NEW_TAB_ID, 'Nueva pestaña', 'new_tab'),
                        _check(LINK_FORCE_RELOAD_ID, 'Forzar recarga', 'force_reload'),
                    ],
                    className='atlanticus-navigation-admin__check-row',
                ),
                html.Div(id=LINK_RESULT_ID),
                html.Div(
                    [
                        html.Button(
                            'Cancelar',
                            id=LINK_CANCEL_ID,
                            n_clicks=0,
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--secondary'
                            ),
                        ),
                        html.Button(
                            'Guardar',
                            id=LINK_SAVE_ID,
                            n_clicks=0,
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--primary'
                            ),
                        ),
                    ],
                    className='atlanticus-navigation-admin__modal-actions',
                ),
            ],
            className='atlanticus-navigation-admin__modal-card',
        ),
        id=LINK_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _group_modal() -> object:
    return html.Div(
        html.Div(
            [
                html.H3(id=GROUP_MODAL_TITLE_ID),
                html.Div(
                    [
                        _field('Nombre', dcc.Input(id=GROUP_NAME_ID, type='text')),
                        _field(
                            'Key',
                            dcc.Input(
                                id=GROUP_KEY_ID,
                                type='text',
                                disabled=True,
                                placeholder='Se genera al guardar',
                            ),
                        ),
                        _field(
                            'Ícono',
                            dcc.Input(
                                id=GROUP_ICON_ID,
                                type='text',
                                placeholder='bi bi-grid',
                            ),
                        ),
                        html.Div(
                            _check(GROUP_ENABLED_ID, 'Habilitada', 'enabled'),
                            className='atlanticus-navigation-admin__field-check',
                        ),
                    ],
                    className='atlanticus-navigation-admin__form-grid',
                ),
                html.Div(id=GROUP_RESULT_ID),
                html.Div(
                    [
                        html.Button(
                            'Cancelar',
                            id=GROUP_CANCEL_ID,
                            n_clicks=0,
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--secondary'
                            ),
                        ),
                        html.Button(
                            'Guardar',
                            id=GROUP_SAVE_ID,
                            n_clicks=0,
                            className=(
                                'atlanticus-manager__button atlanticus-manager__button--primary'
                            ),
                        ),
                    ],
                    className='atlanticus-navigation-admin__modal-actions',
                ),
            ],
            className='atlanticus-navigation-admin__modal-card',
        ),
        id=GROUP_MODAL_ID,
        className=_MODAL_CLOSED,
    )


def _field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label), control],
        className='atlanticus-navigation-admin__field',
    )


def _check(component_id: str, label: str, value: str) -> object:
    return dcc.Checklist(
        id=component_id,
        options=[{'label': label, 'value': value}],
        value=[],
    )
