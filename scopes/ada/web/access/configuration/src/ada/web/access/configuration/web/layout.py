from __future__ import annotations

from collections.abc import Callable

import dash_bootstrap_components as dbc
from dash import dcc, html

from ada.web.access.configuration.editor import build_initial_configuration
from ada.web.access.configuration.models import (
    UNRESTRICTED_ACCESS_PROFILE_KEYS,
    AdaAccessConfiguration,
)
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
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
    VIEW_STORE_ID,
    access_page_id,
    access_remove_id,
    profile_configure_id,
    profile_modal_access_id,
    profile_page_id,
)
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext
from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, Page, PageRequest, paginate_items
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition

_PROFILE_MODAL_CLOSED = 'ada-access-admin__modal'


def build_ada_access_admin_configuration(context: AdaAccessAdminWebContext) -> object:
    configuration = build_initial_configuration()
    profiles = context.profile_catalog_provider()
    access_page = access_catalog_page(configuration, PageRequest())
    profile_page = profile_assignment_page(profiles, PageRequest())
    return html.Div(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=configuration.to_document(),
                storage_type='memory',
            ),
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            dcc.Store(id=VIEW_STORE_ID, data='accesses', storage_type='memory'),
            dcc.Store(id=PROFILE_EDITOR_STORE_ID, storage_type='memory'),
            dcc.Store(id=ACCESS_PAGE_STORE_ID, data=1, storage_type='memory'),
            dcc.Store(id=PROFILE_PAGE_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            _configuration_tabs(),
            html.Div(
                _access_catalog_section(configuration, access_page),
                id=ACCESS_PANEL_ID,
                className='ada-access-admin__tab-panel ada-access-admin__tab-panel--active',
            ),
            html.Div(
                _profile_assignments_section(configuration, profile_page),
                id=PROFILES_PANEL_ID,
                className='ada-access-admin__tab-panel',
            ),
            _save_section(),
            _profile_modal(),
        ],
        className='ada-access-admin atlanticus-bootstrap',
    )


def access_catalog_page(
    configuration: AdaAccessConfiguration,
    request: PageRequest,
) -> Page[str]:
    return paginate_items(configuration.access_keys, request)


def profile_assignment_page(
    profiles: ProfileCatalog | None,
    request: PageRequest,
) -> Page[ProfileDefinition]:
    catalog = profiles if profiles is not None else ProfileCatalog()
    assignable = tuple(
        profile
        for profile in catalog.all()
        if profile.key not in UNRESTRICTED_ACCESS_PROFILE_KEYS
    )
    return paginate_items(assignable, request)


def render_access_catalog(page: Page[str]) -> object:
    if page.items:
        content = [_access_row(access_key) for access_key in page.items]
    else:
        content = [
            _empty_state(
                title='Todavía no hay accesos definidos.',
                copy='Crea el primer identificador mediante un ámbito y un permiso.',
            )
        ]
    results_class = 'ada-access-admin__results'
    if not page.items:
        results_class += ' ada-access-admin__results--empty'
    return html.Div(
        [
            html.Div(content, className=results_class),
            _pagination(page, kind='access'),
        ],
        className='ada-access-admin__paged-list',
        **{
            'data-page-size': str(page.request.page_size),
            'data-total-count': str(page.total_count),
        },
    )


def render_profile_assignments(
    configuration: AdaAccessConfiguration,
    page: Page[ProfileDefinition],
) -> object:
    if page.items:
        content = [_profile_assignment_row(configuration, profile) for profile in page.items]
    else:
        content = [
            _empty_state(
                title='No hay perfiles asignables.',
                copy='Los perfiles configurables aparecerán aquí cuando estén disponibles.',
            )
        ]
    results_class = 'ada-access-admin__results'
    if not page.items:
        results_class += ' ada-access-admin__results--empty'
    return html.Div(
        [
            html.Div(content, className=results_class),
            _pagination(page, kind='profile'),
        ],
        className='ada-access-admin__paged-list',
        **{
            'data-page-size': str(page.request.page_size),
            'data-total-count': str(page.total_count),
        },
    )


def render_profile_access_editor(
    configuration: AdaAccessConfiguration,
    *,
    selected: tuple[str, ...],
) -> object:
    selected_keys = frozenset(selected)
    return [
        dbc.Checkbox(
            id=profile_modal_access_id(access_key),
            label=access_key,
            value=access_key in selected_keys,
            className='ada-access-admin__access-check-row',
            inputClassName='ada-access-admin__access-check-input',
            labelClassName='ada-access-admin__access-check-label',
        )
        for access_key in configuration.access_keys
    ]


def _runtime_context(context: AdaAccessAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Fuente de verdad'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ],
                className='ada-access-admin__runtime-source',
            ),
            html.Div(
                [
                    html.Span('Proyección'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ],
                className='ada-access-admin__runtime-source',
            ),
        ],
        className='ada-access-admin__runtime-context',
    )


def _configuration_tabs() -> object:
    return html.Nav(
        [
            html.Button(
                'Accesos',
                id=ACCESS_TAB_ID,
                n_clicks=0,
                type='button',
                className='ada-access-admin__tab ada-access-admin__tab--active',
            ),
            html.Button(
                'Perfiles',
                id=PROFILES_TAB_ID,
                n_clicks=0,
                type='button',
                className='ada-access-admin__tab',
            ),
        ],
        className='ada-access-admin__tabs',
        **{'aria-label': 'Configuración de accesos'},
    )


def _access_catalog_section(
    configuration: AdaAccessConfiguration,
    page: Page[str],
) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.H3('Accesos definidos'),
                    html.P(
                        'Cada acceso tiene una identidad estable con formato ámbito.permiso. '
                        'El identificador es el valor que consume el código.'
                    ),
                ],
                className='ada-access-admin__section-copy',
            ),
            html.Div(
                [
                    html.Label(
                        [
                            html.Span('Ámbito'),
                            dbc.Input(
                                id=ACCESS_SCOPE_INPUT_ID,
                                type='text',
                                placeholder='alarms',
                            ),
                        ],
                        className='ada-access-admin__create-field',
                    ),
                    html.Span('.', className='ada-access-admin__access-separator'),
                    html.Label(
                        [
                            html.Span('Permiso'),
                            dbc.Input(
                                id=ACCESS_PERMISSION_INPUT_ID,
                                type='text',
                                placeholder='view',
                            ),
                        ],
                        className='ada-access-admin__create-field',
                    ),
                    html.Div(
                        [
                            html.Span('Identificador'),
                            html.Code('alarms.view', id=ACCESS_KEY_PREVIEW_ID),
                        ],
                        className='ada-access-admin__access-preview',
                    ),
                    dbc.Button(
                        '+ Agregar',
                        id=ADD_ACCESS_ID,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                    ),
                ],
                className='ada-access-admin__access-create',
            ),
            html.Div(id=ADD_ACCESS_RESULT_ID),
            html.Div(
                render_access_catalog(page),
                id=ACCESS_LIST_ID,
            ),
        ],
        className='ada-access-admin__section',
    )


def _profile_assignments_section(
    configuration: AdaAccessConfiguration,
    page: Page[ProfileDefinition],
) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.H3('Asignación por perfiles'),
                    html.P(
                        'Configura los accesos de cada perfil. '
                        'Las asignaciones permanecen en el borrador al cambiar de página.'
                    ),
                ],
                className='ada-access-admin__section-copy',
            ),
            html.Div(
                render_profile_assignments(configuration, page),
                id=PROFILE_ASSIGNMENTS_ID,
            ),
        ],
        className='ada-access-admin__section',
    )


def _access_row(access_key: str) -> object:
    scope, separator, permission = access_key.partition('.')
    metadata = (
        html.Small(f'Ámbito: {scope} · Permiso: {permission}')
        if separator and scope and permission
        else html.Small('Identificador estable')
    )
    return html.Article(
        [
            html.Div(
                [
                    html.Code(access_key),
                    metadata,
                ],
                className='ada-access-admin__access-copy',
            ),
            dbc.Button(
                'Eliminar',
                id=access_remove_id(access_key),
                n_clicks=0,
                color='secondary',
                outline=True,
                size='sm',
            ),
        ],
        className='ada-access-admin__access-row',
    )


def _profile_assignment_row(
    configuration: AdaAccessConfiguration,
    profile: ProfileDefinition,
) -> object:
    grant = next(
        (item for item in configuration.profile_access if item.profile_key == profile.key),
        None,
    )
    assigned_count = 0 if grant is None else len(grant.access_keys)
    has_access_catalog = bool(configuration.access_keys)
    return html.Article(
        [
            html.Div(
                [
                    html.Span(
                        profile.label,
                        className='ada-access-admin__profile-badge',
                        style={
                            'backgroundColor': profile.background_color,
                            'color': profile.text_color,
                        },
                    ),
                    html.Code(profile.key),
                ],
                className='ada-access-admin__profile-copy',
            ),
            html.Div(
                [
                    html.Span(
                        _assigned_access_text(assigned_count),
                        className='ada-access-admin__profile-access-count',
                    ),
                    dbc.Button(
                        'Configurar',
                        id=profile_configure_id(profile.key),
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not has_access_catalog,
                    ),
                ],
                className='ada-access-admin__profile-actions',
            ),
        ],
        className='ada-access-admin__profile-row',
    )


def _profile_modal() -> object:
    return html.Div(
        [
            html.Button(
                id=PROFILE_MODAL_BACKDROP_ID,
                className='ada-access-admin__modal-backdrop',
                type='button',
                **{'aria-label': 'Cerrar configuración de accesos'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.H2(id=PROFILE_MODAL_TITLE_ID),
                                    html.P('Selecciona los accesos asignados a este perfil.'),
                                ],
                                className='ada-access-admin__modal-heading',
                            ),
                            html.Button(
                                id=PROFILE_MODAL_CLOSE_ID,
                                n_clicks=0,
                                type='button',
                                className='btn-close',
                                **{'aria-label': 'Cerrar configuración de accesos'},
                            ),
                        ],
                        className='modal-header ada-access-admin__modal-header',
                    ),
                    html.Div(
                        [
                            html.Div(
                                id=PROFILE_MODAL_ACCESS_LIST_ID,
                                className='ada-access-admin__access-checklist-shell',
                            ),
                            html.Div(id=PROFILE_MODAL_RESULT_ID),
                        ],
                        className='modal-body ada-access-admin__modal-body',
                    ),
                    html.Footer(
                        [
                            dbc.Button(
                                'Cancelar',
                                id=PROFILE_MODAL_CANCEL_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                            dbc.Button(
                                'Guardar',
                                id=PROFILE_MODAL_SAVE_ID,
                                n_clicks=0,
                                color='primary',
                            ),
                        ],
                        className='modal-footer ada-access-admin__modal-actions',
                    ),
                ],
                className='modal-content ada-access-admin__modal-card',
            ),
        ],
        id=PROFILE_MODAL_ID,
        className=_PROFILE_MODAL_CLOSED,
    )


def _pagination(page: Page[object], *, kind: str) -> object:
    if kind == 'access':
        previous_id = ACCESS_PREVIOUS_ID
        next_id = ACCESS_NEXT_ID
        page_size_id = ACCESS_PAGE_SIZE_ID
        page_id_factory: Callable[[int], object] = access_page_id
    else:
        previous_id = PROFILE_PREVIOUS_ID
        next_id = PROFILE_NEXT_ID
        page_size_id = PROFILE_PAGE_SIZE_ID
        page_id_factory = profile_page_id
    return html.Div(
        [
            html.Div(
                _pagination_summary(page),
                className='ada-access-admin__pagination-summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id=previous_id,
                        type='button',
                        disabled=not page.has_previous,
                        className='ada-access-admin__pagination-button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *_page_buttons(page, page_id_factory),
                    html.Button(
                        '›',
                        id=next_id,
                        type='button',
                        disabled=not page.has_next,
                        className='ada-access-admin__pagination-button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='ada-access-admin__pagination-navigation',
            ),
            html.Label(
                [
                    html.Span(
                        'Filas',
                        className='ada-access-admin__pagination-page-size-label',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=page_size_id,
                            options=[
                                {'label': str(value), 'value': value}
                                for value in ALLOWED_PAGE_SIZES
                            ],
                            value=page.request.page_size,
                            clearable=False,
                            searchable=False,
                            style=_select_style(),
                        ),
                        className='ada-access-admin__pagination-page-size',
                    ),
                ],
                className='ada-access-admin__pagination-page-size-control',
            ),
        ],
        className='ada-access-admin__pagination',
        **{
            'data-page': str(page.request.page_number),
            'data-page-count': str(page.page_count),
            'data-total-count': str(page.total_count),
        },
    )


def _page_buttons(
    page: Page[object],
    page_id_factory: Callable[[int], object],
) -> list[object]:
    nodes: list[object] = []
    for value in _visible_page_tokens(
        current=page.request.page_number,
        total=page.page_count,
    ):
        if value is None:
            nodes.append(
                html.Span(
                    '…',
                    className='ada-access-admin__pagination-ellipsis',
                    **{'aria-hidden': 'true'},
                )
            )
            continue
        current = value == page.request.page_number
        nodes.append(
            html.Button(
                str(value),
                id=page_id_factory(value),
                type='button',
                disabled=current,
                className=(
                    'ada-access-admin__pagination-button '
                    'ada-access-admin__pagination-button--active'
                    if current
                    else 'ada-access-admin__pagination-button'
                ),
                **{
                    'aria-label': f'Página {value}',
                    'aria-current': 'page' if current else 'false',
                },
            )
        )
    return nodes


def _pagination_summary(page: Page[object]) -> str:
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


def _assigned_access_text(count: int) -> str:
    if count == 0:
        return 'Sin accesos'
    if count == 1:
        return '1 acceso'
    return f'{count} accesos'


def _empty_state(*, title: str, copy: str) -> object:
    return html.Div(
        [
            html.Span('+', className='ada-access-admin__empty-icon', **{'aria-hidden': 'true'}),
            html.Strong(title),
            html.Span(copy),
        ],
        className='ada-access-admin__empty-state',
        role='status',
    )


def _save_section() -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3('Borrador local · accesos'),
                            html.P(
                                'Guarda las definiciones y asignaciones en el workspace '
                                'de este navegador.'
                            ),
                        ],
                        className='ada-access-admin__section-copy',
                    ),
                    dbc.Button(
                        'Guardar borrador',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        color='primary',
                    ),
                ],
                className='ada-access-admin__section-heading',
            ),
            html.Div(id=SAVE_RESULT_ID),
        ],
        className='ada-access-admin__section ada-access-admin__section--footer',
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
