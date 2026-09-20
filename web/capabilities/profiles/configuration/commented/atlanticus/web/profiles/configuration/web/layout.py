from __future__ import annotations

# La UI presenta Profiles sin trasladar ownership a Manager.
# Los perfiles normales usan una inicial; Local es el único caso especial y muestra sus identidades locales.
# El editor conserva nombre y colores como único contrato editable, añadiendo sólo feedback visual.

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
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
    profile_edit_id,
    profile_page_id,
)
from atlanticus.web.profiles.configuration.web.models import (
    LocalIdentityBadge,
    ProfilesAdminWebContext,
    build_profile_avatar_text,
)
from atlanticus.web.profiles.models import (
    BASIC_PROFILE_KEY,
    GUEST_PROFILE_KEY,
    LOCAL_PROFILE_KEY,
    ROOT_PROFILE_KEY,
    SYSTEM_PROFILE_DEFINITIONS,
    ProfileDefinition,
)

_PROFILE_MODAL_CLOSED = 'atlanticus-profiles-admin__modal'
_SYSTEM_PROFILE_DESCRIPTIONS = {
    BASIC_PROFILE_KEY: (
        'Perfil base disponible desde el inicio para promover usuarios aun cuando no '
        'existan perfiles configurados.'
    ),
    ROOT_PROFILE_KEY: 'Perfil del sistema con acceso completo.',
    GUEST_PROFILE_KEY: (
        'Perfil base para usuarios que operan como invitados sin un perfil personalizado.'
    ),
    LOCAL_PROFILE_KEY: (
        'Acceso completo al sistema en modo local de desarrollo. Su apariencia depende de la '
        'identidad local activa.'
    ),
}


def build_profiles_admin_configuration(context: ProfilesAdminWebContext) -> object:
    configuration = build_initial_configuration()
    page = configured_profiles_page(
        configuration,
        PageRequest(page_number=1, page_size=DEFAULT_PAGE_SIZE),
    )
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
            _configured_profiles_section(page),
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
    if page.items:
        content = [_configured_profile_row(profile) for profile in page.items]
    else:
        content = [
            _empty_state(
                title='Todavía no hay perfiles configurados.',
                copy='Agrega el primer perfil para comenzar.',
            )
        ]
    results_class = 'atlanticus-profiles-admin__configured-results'
    if not page.items:
        results_class += ' atlanticus-profiles-admin__configured-results--empty'
    return html.Div(
        [
            html.Div(content, className=results_class),
            _pagination(page),
        ],
        className='atlanticus-profiles-admin__paged-list',
        **{
            'data-page-size': str(page.request.page_size),
            'data-total-count': str(page.total_count),
        },
    )


def _runtime_context(context: ProfilesAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ],
                className='atlanticus-profiles-admin__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ],
                className='atlanticus-profiles-admin__runtime-source',
            ),
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
    if profile.key == LOCAL_PROFILE_KEY:
        return html.Article(
            [
                html.Div(
                    [
                        html.Strong(profile.label),
                        html.P(_SYSTEM_PROFILE_DESCRIPTIONS[profile.key]),
                    ],
                    className='atlanticus-profiles-admin__system-copy',
                ),
                html.Div(
                    [
                        html.Small(
                            'Identidades locales',
                            className='atlanticus-profiles-admin__local-identities-label',
                        ),
                        html.Div(
                            [_local_identity_preview(badge) for badge in local_badges],
                            className='atlanticus-profiles-admin__local-identities',
                        ),
                    ],
                    className='atlanticus-profiles-admin__local-identities-block',
                ),
            ],
            className=(
                'atlanticus-profiles-admin__system-card '
                'atlanticus-profiles-admin__system-card--local'
            ),
        )
    return html.Article(
        [
            html.Div(
                [
                    _profile_avatar(
                        profile.label,
                        profile.background_color,
                        profile.text_color,
                    ),
                    html.Strong(profile.label),
                ],
                className='atlanticus-profiles-admin__system-profile-heading',
            ),
            html.P(
                _SYSTEM_PROFILE_DESCRIPTIONS[profile.key],
                className='atlanticus-profiles-admin__system-description',
            ),
        ],
        className='atlanticus-profiles-admin__system-card',
    )

def _configured_profiles_section(page: Page[ProfileDefinition]) -> object:
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
            ),
        ],
        className='atlanticus-profiles-admin__section',
    )


def _configured_profile_row(profile: ProfileDefinition) -> object:
    return html.Article(
        [
            html.Div(
                [
                    _profile_avatar(
                        profile.label,
                        profile.background_color,
                        profile.text_color,
                    ),
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
                        className='atlanticus-profiles-admin__row-details',
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
                _pagination_summary(page),
                className='atlanticus-profiles-admin__pagination-summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id=PREVIOUS_PAGE_ID,
                        type='button',
                        disabled=not page.has_previous,
                        className='atlanticus-profiles-admin__pagination-button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *_page_buttons(page),
                    html.Button(
                        '›',
                        id=NEXT_PAGE_ID,
                        type='button',
                        disabled=not page.has_next,
                        className='atlanticus-profiles-admin__pagination-button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='atlanticus-profiles-admin__pagination-navigation',
            ),
            html.Label(
                [
                    html.Span(
                        'Filas',
                        className='atlanticus-profiles-admin__pagination-page-size-label',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=PAGE_SIZE_ID,
                            options=[
                                {'label': str(value), 'value': value}
                                for value in ALLOWED_PAGE_SIZES
                            ],
                            value=page.request.page_size,
                            clearable=False,
                            searchable=False,
                            style=_select_style(),
                        ),
                        className='atlanticus-profiles-admin__pagination-page-size',
                    ),
                ],
                className='atlanticus-profiles-admin__pagination-page-size-control',
            ),
        ],
        className='atlanticus-profiles-admin__pagination',
        **{
            'data-page': str(page.request.page_number),
            'data-page-count': str(page.page_count),
            'data-total-count': str(page.total_count),
        },
    )


def _page_buttons(page: Page[ProfileDefinition]) -> list[object]:
    nodes: list[object] = []
    for value in _visible_page_tokens(
        current=page.request.page_number,
        total=page.page_count,
    ):
        if value is None:
            nodes.append(
                html.Span(
                    '…',
                    className='atlanticus-profiles-admin__pagination-ellipsis',
                    **{'aria-hidden': 'true'},
                )
            )
            continue
        current = value == page.request.page_number
        nodes.append(
            html.Button(
                str(value),
                id=profile_page_id(value),
                type='button',
                disabled=current,
                className=(
                    'atlanticus-profiles-admin__pagination-button '
                    'atlanticus-profiles-admin__pagination-button--active'
                    if current
                    else 'atlanticus-profiles-admin__pagination-button'
                ),
                **{
                    'aria-label': f'Página {value}',
                    'aria-current': 'page' if current else 'false',
                },
            )
        )
    return nodes


def _pagination_summary(page: Page[ProfileDefinition]) -> str:
    if page.total_count == 0:
        return 'Mostrando 0 de 0'
    return f'Mostrando {page.start_index}–{page.end_index} de {page.total_count}'


def _visible_page_tokens(*, current: int, total: int) -> tuple[int | None, ...]:
    if total <= 7:
        return tuple(range(1, total + 1))
    selected = {1, total, current}
    for candidate in (current - 1, current + 1):
        if 1 < candidate < total:
            selected.add(candidate)
    ordered = sorted(selected)
    tokens: list[int | None] = []
    previous: int | None = None
    for value in ordered:
        if previous is not None and value - previous > 1:
            tokens.append(None)
        tokens.append(value)
        previous = value
    return tuple(tokens)


def _empty_state(*, title: str, copy: str) -> object:
    return html.Div(
        [
            html.Span(
                '+',
                className='atlanticus-profiles-admin__empty-icon',
                **{'aria-hidden': 'true'},
            ),
            html.Strong(title),
            html.Span(copy),
        ],
        className='atlanticus-profiles-admin__empty-state',
        role='status',
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
                                'Guarda los perfiles configurados en el workspace de este '
                                'navegador.'
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
    return html.Div(
        [
            html.Button(
                id=PROFILE_MODAL_BACKDROP_ID,
                n_clicks=0,
                type='button',
                className='atlanticus-profiles-admin__modal-backdrop',
                **{'aria-label': 'Cerrar editor de perfil'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.H2(id=PROFILE_MODAL_TITLE_ID),
                                    html.P('Define el nombre y los colores visibles del perfil.'),
                                ],
                                className='atlanticus-profiles-admin__modal-heading',
                            ),
                            html.Button(
                                id=PROFILE_MODAL_CLOSE_ID,
                                n_clicks=0,
                                type='button',
                                className='btn-close',
                                **{'aria-label': 'Cerrar editor de perfil'},
                            ),
                        ],
                        className='modal-header atlanticus-profiles-admin__modal-header',
                    ),
                    html.Div(
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
                                    _color_field(
                                        'Color de fondo',
                                        component_id=PROFILE_BACKGROUND_COLOR_ID,
                                        value_id=PROFILE_BACKGROUND_COLOR_VALUE_ID,
                                        value='#123456',
                                    ),
                                    _color_field(
                                        'Color de texto',
                                        component_id=PROFILE_TEXT_COLOR_ID,
                                        value_id=PROFILE_TEXT_COLOR_VALUE_ID,
                                        value='#FFFFFF',
                                    ),
                                ],
                                className='atlanticus-profiles-admin__color-grid',
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        'N',
                                        id=PROFILE_PREVIEW_AVATAR_ID,
                                        className=(
                                            'atlanticus-profiles-admin__avatar '
                                            'atlanticus-profiles-admin__modal-preview-avatar'
                                        ),
                                        style={
                                            'backgroundColor': '#123456',
                                            'color': '#FFFFFF',
                                        },
                                    ),
                                    html.Div(
                                        [
                                            html.Small('Vista previa'),
                                            html.Strong(
                                                'Nuevo perfil',
                                                id=PROFILE_PREVIEW_LABEL_ID,
                                            ),
                                        ],
                                        className='atlanticus-profiles-admin__modal-preview-copy',
                                    ),
                                ],
                                className='atlanticus-profiles-admin__modal-preview',
                            ),
                            html.Div(id=PROFILE_RESULT_ID),
                        ],
                        className='modal-body atlanticus-profiles-admin__modal-body',
                    ),
                    html.Footer(
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
                        ],
                        className='modal-footer atlanticus-profiles-admin__modal-actions',
                    ),
                ],
                className='modal-content atlanticus-profiles-admin__modal-card',
            ),
        ],
        id=PROFILE_MODAL_ID,
        className=_PROFILE_MODAL_CLOSED,
    )


def _field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label), control],
        className='atlanticus-profiles-admin__field',
    )


def _color_field(
    label: str,
    *,
    component_id: str,
    value_id: str,
    value: str,
) -> object:
    return html.Label(
        [
            html.Span(label),
            html.Div(
                [
                    dbc.Input(
                        id=component_id,
                        type='color',
                        value=value,
                        className='atlanticus-profiles-admin__color-input',
                    ),
                    html.Code(value, id=value_id),
                ],
                className='atlanticus-profiles-admin__color-control',
            ),
        ],
        className='atlanticus-profiles-admin__field',
    )


def _profile_avatar(label: str, background_color: str, text_color: str) -> object:
    return html.Span(
        build_profile_avatar_text(label),
        className='atlanticus-profiles-admin__avatar',
        style={
            'backgroundColor': background_color,
            'color': text_color,
        },
        **{'aria-hidden': 'true'},
    )


def _local_identity_preview(badge: LocalIdentityBadge) -> object:
    return html.Div(
        [
            html.Span(
                badge.avatar_text,
                className='atlanticus-profiles-admin__avatar',
                style={
                    'backgroundColor': badge.background_color,
                    'color': badge.text_color,
                },
                **{'aria-hidden': 'true'},
            ),
            html.Strong(badge.display_name),
        ],
        className='atlanticus-profiles-admin__local-identity',
    )


def _color_swatch(color: str) -> object:
    return html.Span(
        className='atlanticus-profiles-admin__swatch',
        style={'backgroundColor': color},
        title=color,
    )


def _select_style() -> dict[str, str]:
    return {
        '--Dash-Spacing': '4px',
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-secondary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-secondary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }
