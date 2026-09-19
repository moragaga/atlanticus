from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from atlanticus.web.pagination import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    Page,
    PageRequest,
    paginate_items,
)
from atlanticus.web.profiles.configuration.editor import build_initial_configuration
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
    SOURCE_NAME_ID,
    profile_edit_id,
)
from atlanticus.web.profiles.configuration.web.models import (
    LocalIdentityBadge,
    ProfilesAdminWebContext,
)
from atlanticus.web.profiles.models import (
    LOCAL_PROFILE_KEY,
    SYSTEM_PROFILE_DEFINITIONS,
    ProfileDefinition,
)


def build_profiles_admin_configuration(context: ProfilesAdminWebContext) -> object:
    configuration = build_initial_configuration()
    return html.Div(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=configuration.to_document(),
                storage_type='memory',
            ),
            dcc.Store(id=EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(
                id=PAGE_STORE_ID,
                data={'page_number': 1, 'page_size': DEFAULT_PAGE_SIZE},
                storage_type='memory',
            ),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            _system_profiles_section(context),
            _configured_profiles_section(configuration),
            _save_section(),
            _profile_modal(),
        ],
        className='atlanticus-profiles-admin atlanticus-bootstrap',
    )


def configured_profiles_page(
    configuration: ProfilesConfiguration,
    request: PageRequest,
) -> Page[ProfileDefinition]:
    return paginate_items(configuration.profiles, request)


def render_configured_profiles(page: Page[ProfileDefinition]) -> object:
    if not page.items:
        return html.P(
            'No hay perfiles configurados.',
            className='atlanticus-profiles-admin__empty',
        )
    return [_configured_profile_row(profile) for profile in page.items]


def page_status(page: Page[ProfileDefinition]) -> str:
    if page.total_count == 0:
        return '0 perfiles'
    return f'{page.start_index}–{page.end_index} de {page.total_count}'


def _runtime_context(context: ProfilesAdminWebContext) -> object:
    return html.Section(
        [
            html.Span('Fuente de verdad'),
            html.Strong(context.source_name, id=SOURCE_NAME_ID),
        ],
        className='atlanticus-profiles-admin__runtime-context',
    )


def _system_profiles_section(context: ProfilesAdminWebContext) -> object:
    local_badges = context.local_identity_badges_provider()
    cards = [
        _system_profile_card(
            profile,
            local_badges=local_badges if profile.key == LOCAL_PROFILE_KEY else (),
        )
        for profile in SYSTEM_PROFILE_DEFINITIONS
    ]
    return html.Section(
        [
            html.Div(
                [
                    html.H3('Perfiles del sistema'),
                    html.P(
                        'Siempre disponibles. Sus nombres y colores requieren despliegue '
                        'para cambiarse.'
                    ),
                ],
                className='atlanticus-profiles-admin__section-copy',
            ),
            html.Div(cards, className='atlanticus-profiles-admin__system-grid'),
        ],
        className='atlanticus-profiles-admin__section',
    )


def _system_profile_card(
    profile: ProfileDefinition,
    *,
    local_badges: tuple[LocalIdentityBadge, ...] = (),
) -> object:
    details: list[object] = [
        _profile_color_badge(
            profile.label,
            profile.background_color,
            profile.text_color,
        )
    ]
    if local_badges:
        details.append(
            html.Div(
                [
                    _profile_color_badge(
                        badge.display_name,
                        badge.background_color,
                        badge.text_color,
                    )
                    for badge in local_badges
                ],
                className='atlanticus-profiles-admin__local-identities',
            )
        )
    return html.Article(
        details,
        className='atlanticus-profiles-admin__system-card',
    )


def _configured_profiles_section(configuration: ProfilesConfiguration) -> object:
    page = configured_profiles_page(
        configuration,
        PageRequest(page_number=1, page_size=DEFAULT_PAGE_SIZE),
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Perfiles configurados'),
                            html.P(
                                'El nombre y los colores son editables. La identidad técnica '
                                'se mantiene internamente.'
                            ),
                        ],
                        className='atlanticus-profiles-admin__section-copy',
                    ),
                    dbc.Button(
                        '+ Perfil',
                        id=ADD_PROFILE_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                    ),
                ],
                className='atlanticus-profiles-admin__section-heading',
            ),
            html.Div(
                render_configured_profiles(page),
                id=CONFIGURED_PROFILES_ID,
                className='atlanticus-profiles-admin__configured-list',
            ),
            _pagination(page),
        ],
        className='atlanticus-profiles-admin__section',
    )


def _configured_profile_row(profile: ProfileDefinition) -> object:
    return html.Article(
        [
            html.Div(
                [
                    html.Strong(profile.label),
                    html.Div(
                        [
                            _color_swatch(profile.background_color),
                            html.Small(profile.background_color),
                            _color_swatch(profile.text_color),
                            html.Small(profile.text_color),
                        ],
                        className='atlanticus-profiles-admin__row-colors',
                    ),
                ],
                className='atlanticus-profiles-admin__row-copy',
            ),
            dbc.Button(
                'Editar',
                id=profile_edit_id(profile.key),
                n_clicks=0,
                color='secondary',
                outline=True,
                size='sm',
            ),
        ],
        className='atlanticus-profiles-admin__profile-row',
    )


def _pagination(page: Page[ProfileDefinition]) -> object:
    return html.Div(
        [
            html.Div(
                [
                    html.Span('Filas'),
                    dcc.Dropdown(
                        id=PAGE_SIZE_ID,
                        options=[
                            {'label': str(size), 'value': size}
                            for size in ALLOWED_PAGE_SIZES
                        ],
                        value=page.request.page_size,
                        clearable=False,
                        searchable=False,
                        className='atlanticus-profiles-admin__page-size',
                    ),
                ],
                className='atlanticus-profiles-admin__page-size-control',
            ),
            html.Span(page_status(page), id=PAGE_STATUS_ID),
            html.Div(
                [
                    dbc.Button(
                        'Anterior',
                        id=PREVIOUS_PAGE_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not page.has_previous,
                    ),
                    dbc.Button(
                        'Siguiente',
                        id=NEXT_PAGE_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not page.has_next,
                    ),
                ],
                className='atlanticus-profiles-admin__page-actions',
            ),
        ],
        className='atlanticus-profiles-admin__pagination',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · perfiles'),
                            html.P(
                                'Guarda los perfiles configurados en el workspace de este navegador.'
                            ),
                        ],
                        className='atlanticus-profiles-admin__section-copy',
                    ),
                    dbc.Button(
                        'Guardar borrador',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        color='primary',
                    ),
                ],
                className='atlanticus-profiles-admin__section-heading',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className=(
            'atlanticus-profiles-admin__section '
            'atlanticus-profiles-admin__section--footer'
        ),
    )


def _profile_modal() -> object:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id=PROFILE_MODAL_TITLE_ID),
                close_button=False,
            ),
            dbc.ModalBody(
                [
                    _field(
                        'Nombre',
                        dbc.Input(
                            id=PROFILE_NAME_ID,
                            type='text',
                            placeholder='Nombre visible del perfil',
                        ),
                    ),
                    html.Div(
                        [
                            _field(
                                'Color de fondo',
                                dbc.Input(
                                    id=PROFILE_BACKGROUND_COLOR_ID,
                                    type='color',
                                    value='#123456',
                                ),
                            ),
                            _field(
                                'Color de texto',
                                dbc.Input(
                                    id=PROFILE_TEXT_COLOR_ID,
                                    type='color',
                                    value='#FFFFFF',
                                ),
                            ),
                        ],
                        className='atlanticus-profiles-admin__color-grid',
                    ),
                    html.Div(id=PROFILE_RESULT_ID),
                ],
                className='atlanticus-profiles-admin__modal-body',
            ),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        'Cancelar',
                        id=PROFILE_CANCEL_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                    ),
                    dbc.Button(
                        'Guardar',
                        id=PROFILE_SAVE_ID,
                        n_clicks=0,
                        color='primary',
                    ),
                ]
            ),
        ],
        id=PROFILE_MODAL_ID,
        is_open=False,
        centered=True,
    )


def _field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label), control],
        className='atlanticus-profiles-admin__field',
    )


def _profile_color_badge(label: str, background_color: str, text_color: str) -> object:
    return html.Span(
        label,
        className='atlanticus-profiles-admin__profile-badge',
        style={
            'backgroundColor': background_color,
            'color': text_color,
        },
    )


def _color_swatch(color: str) -> object:
    return html.Span(
        className='atlanticus-profiles-admin__swatch',
        style={'backgroundColor': color},
        title=color,
    )
