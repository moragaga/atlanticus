from __future__ import annotations

from collections.abc import Callable

import dash_bootstrap_components as dbc
from dash import dcc, html

from atlanticus.web.pagination import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    Page,
    PageRequest,
    paginate_items,
)
from atlanticus.web.users.web.ids import (
    EDIT_BACKDROP_ID,
    EDIT_CANCEL_ID,
    EDIT_CLOSE_ID,
    EDIT_ENABLED_ID,
    EDIT_IDENTITY_ID,
    EDIT_MODAL_ID,
    EDIT_PROFILE_ID,
    EDIT_RESULT_ID,
    EDIT_SAVE_ID,
    EDIT_SELECTED_ID,
    EDIT_TITLE_ID,
    MANAGED_ENABLED_ID,
    MANAGED_LIST_ID,
    MANAGED_NEXT_ID,
    MANAGED_PAGE_ID,
    MANAGED_PAGE_SIZE_ID,
    MANAGED_PANEL_ID,
    MANAGED_PREVIOUS_ID,
    MANAGED_PROFILE_ID,
    MANAGED_ROWS_ID,
    MANAGED_SEARCH_ID,
    MANAGED_STATUS_ID,
    MANAGED_TAB_ID,
    PROMOTION_LIST_ID,
    PROMOTION_NEXT_ID,
    PROMOTION_PAGE_ID,
    PROMOTION_PAGE_SIZE_ID,
    PROMOTION_PANEL_ID,
    PROMOTION_PREVIOUS_ID,
    PROMOTION_RESULT_ID,
    PROMOTION_ROWS_ID,
    PROMOTION_SEARCH_ID,
    PROMOTION_STATE_ID,
    PROMOTION_STATUS_ID,
    PROMOTION_TAB_ID,
    REFRESH_ID,
    REFRESH_RESULT_ID,
    SNAPSHOT_ID,
    VIEW_ID,
    candidate_profile_id,
    candidate_promote_id,
    managed_edit_id,
    managed_page_number_id,
    promotion_page_number_id,
)
from atlanticus.web.users.web.models import UsersAdminWebContext
from atlanticus.web.users.web.serialization import snapshot_to_document


def build_users_admin_configuration(context: UsersAdminWebContext) -> object:
    try:
        snapshot = snapshot_to_document(context.administration.discover())
        error = None
    except Exception:
        snapshot = {'registry_version': None, 'profiles': [], 'candidates': []}
        error = 'Could not load Users Administration.'
    return html.Div(
        [
            dcc.Store(id=SNAPSHOT_ID, data=snapshot, storage_type='memory'),
            dcc.Store(id=VIEW_ID, data='managed', storage_type='memory'),
            dcc.Store(id=PROMOTION_PAGE_ID, data=1, storage_type='memory'),
            dcc.Store(id=MANAGED_PAGE_ID, data=1, storage_type='memory'),
            dcc.Store(id=EDIT_SELECTED_ID, storage_type='memory'),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3('Control de usuarios'),
                                    html.P(
                                        'Administra usuarios del runtime. Las promociones y los '
                                        'cambios guardados se aplican directamente.'
                                    ),
                                ],
                                className='atlanticus-users-admin__section-copy',
                            ),
                            dbc.Button(
                                'Actualizar',
                                id=REFRESH_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                        ],
                        className='atlanticus-users-admin__section-heading',
                    ),
                    html.Div(error, className='atlanticus-users-admin__error') if error else None,
                    html.Div(id=REFRESH_RESULT_ID),
                ],
                className='atlanticus-users-admin__section atlanticus-users-admin__intro',
            ),
            html.Nav(
                [
                    html.Button(
                        'Usuarios',
                        id=MANAGED_TAB_ID,
                        n_clicks=0,
                        type='button',
                        className=view_tab_class(True),
                    ),
                    html.Button(
                        'Por promover',
                        id=PROMOTION_TAB_ID,
                        n_clicks=0,
                        type='button',
                        className=view_tab_class(False),
                    ),
                ],
                className='atlanticus-users-admin__tabs',
                **{'aria-label': 'Administración de usuarios'},
            ),
            html.Div(
                _managed_section(snapshot, can_manage=context.can_manage()),
                id=MANAGED_PANEL_ID,
                className=view_panel_class(True),
            ),
            html.Div(
                _promotion_section(snapshot, can_manage=context.can_manage()),
                id=PROMOTION_PANEL_ID,
                className=view_panel_class(False),
            ),
            _edit_modal(snapshot, can_manage=context.can_manage()),
        ],
        className='atlanticus-users-admin atlanticus-bootstrap',
    )


def render_promotion_rows(
    document: dict[str, object] | None,
    *,
    query: str | None,
    state_filter: str | None,
    page_number: int,
    page_size: int,
    can_manage: bool,
):
    profiles = _profiles(document)
    candidates = tuple(
        candidate
        for candidate in _candidates(document)
        if candidate.get('state') != 'promoted'
        and _matches_search(candidate, query)
        and (state_filter in (None, '', 'all') or candidate.get('state') == state_filter)
    )
    page = paginate_items(candidates, PageRequest(page_number=page_number, page_size=page_size))
    rows = tuple(_promotion_row(candidate, profiles, can_manage=can_manage) for candidate in page.items)
    return rows or (
        _empty_state(
            title='No hay usuarios por promover.',
            copy='Los candidatos disponibles aparecerán aquí cuando sean descubiertos.',
        ),
    ), page


def render_managed_rows(
    document: dict[str, object] | None,
    *,
    query: str | None,
    profile_filter: str | None,
    enabled_filter: str | None,
    page_number: int,
    page_size: int,
    can_manage: bool,
):
    candidates = tuple(
        candidate
        for candidate in _candidates(document)
        if candidate.get('state') == 'promoted'
        and _matches_search(candidate, query)
        and _matches_managed_profile(candidate, profile_filter)
        and _matches_enabled(candidate, enabled_filter)
    )
    page = paginate_items(candidates, PageRequest(page_number=page_number, page_size=page_size))
    rows = tuple(_managed_row(candidate, can_manage=can_manage) for candidate in page.items)
    return rows or (
        _empty_state(
            title='No hay usuarios administrados.',
            copy='Los usuarios promovidos aparecerán aquí cuando estén disponibles.',
        ),
    ), page


def render_promotion_list(
    document: dict[str, object] | None,
    *,
    query: str | None,
    state_filter: str | None,
    page_number: int,
    page_size: int,
    can_manage: bool,
) -> tuple[object, Page[dict[str, object]]]:
    rows, page = render_promotion_rows(
        document,
        query=query,
        state_filter=state_filter,
        page_number=page_number,
        page_size=page_size,
        can_manage=can_manage,
    )
    return _paged_list(
        rows=rows,
        page=page,
        rows_id=PROMOTION_ROWS_ID,
        status_id=PROMOTION_STATUS_ID,
        previous_id=PROMOTION_PREVIOUS_ID,
        next_id=PROMOTION_NEXT_ID,
        page_size_id=PROMOTION_PAGE_SIZE_ID,
        page_id_factory=promotion_page_number_id,
    ), page


def render_managed_list(
    document: dict[str, object] | None,
    *,
    query: str | None,
    profile_filter: str | None,
    enabled_filter: str | None,
    page_number: int,
    page_size: int,
    can_manage: bool,
) -> tuple[object, Page[dict[str, object]]]:
    rows, page = render_managed_rows(
        document,
        query=query,
        profile_filter=profile_filter,
        enabled_filter=enabled_filter,
        page_number=page_number,
        page_size=page_size,
        can_manage=can_manage,
    )
    return _paged_list(
        rows=rows,
        page=page,
        rows_id=MANAGED_ROWS_ID,
        status_id=MANAGED_STATUS_ID,
        previous_id=MANAGED_PREVIOUS_ID,
        next_id=MANAGED_NEXT_ID,
        page_size_id=MANAGED_PAGE_SIZE_ID,
        page_id_factory=managed_page_number_id,
    ), page


def page_status(page: Page[object]) -> str:
    if page.total_count == 0:
        return '0 de 0'
    return f'{page.start_index}–{page.end_index} de {page.total_count}'


def view_tab_class(active: bool) -> str:
    base = 'atlanticus-users-admin__tab'
    return f'{base} {base}--active' if active else base


def view_panel_class(active: bool) -> str:
    base = 'atlanticus-users-admin__tab-panel'
    return f'{base} {base}--active' if active else base


def identity_details(user: dict[str, object] | None) -> object:
    if not isinstance(user, dict):
        return _empty_state(
            title='Identidad no disponible.',
            copy='Actualiza la vista e intenta nuevamente.',
        )
    return html.Div(
        [
            _identity_item('Nombre', user.get('display_name')),
            _identity_item('Email', user.get('email')),
            _identity_item('Issuer', user.get('issuer')),
            _identity_item('Subject ID', user.get('subject_id')),
            _identity_item('User ID', user.get('user_id')),
        ],
        className='atlanticus-users-admin__identity-grid',
    )


def _promotion_section(document: dict[str, object], *, can_manage: bool) -> object:
    paged_list, _page = render_promotion_list(
        document,
        query=None,
        state_filter='all',
        page_number=1,
        page_size=DEFAULT_PAGE_SIZE,
        can_manage=can_manage,
    )
    return html.Section(
        [
            _section_header(
                'Por promover',
                'Identidades conocidas que todavía no forman parte del runtime administrado.',
            ),
            html.Div(
                [
                    _filter_field(
                        'Buscar candidatos',
                        dbc.Input(
                            id=PROMOTION_SEARCH_ID,
                            type='search',
                            placeholder='Nombre, email o identidad',
                        ),
                    ),
                    _filter_field(
                        'Estado',
                        dcc.Dropdown(
                            id=PROMOTION_STATE_ID,
                            options=[
                                {'label': 'Todos', 'value': 'all'},
                                {'label': 'Promovibles', 'value': 'promotable'},
                                {'label': 'Conflictos', 'value': 'conflict'},
                            ],
                            value='all',
                            clearable=False,
                            searchable=False,
                        ),
                    ),
                ],
                className='atlanticus-users-admin__filters',
            ),
            html.Div(paged_list, id=PROMOTION_LIST_ID),
            html.Div(id=PROMOTION_RESULT_ID),
        ],
        className='atlanticus-users-admin__section atlanticus-users-admin__view-section',
    )


def _managed_section(document: dict[str, object], *, can_manage: bool) -> object:
    paged_list, _page = render_managed_list(
        document,
        query=None,
        profile_filter='all',
        enabled_filter='all',
        page_number=1,
        page_size=DEFAULT_PAGE_SIZE,
        can_manage=can_manage,
    )
    profile_options = [{'label': 'Todos los perfiles', 'value': 'all'}] + [
        {'label': str(profile.get('label') or profile.get('key')), 'value': profile.get('key')}
        for profile in _profiles(document)
    ]
    return html.Section(
        [
            _section_header(
                'Usuarios administrados',
                'Usuarios promovidos. La identidad es informativa; solo el perfil y el estado son editables.',
            ),
            html.Div(
                [
                    _filter_field(
                        'Buscar usuarios',
                        dbc.Input(
                            id=MANAGED_SEARCH_ID,
                            type='search',
                            placeholder='Nombre, email o identidad',
                        ),
                    ),
                    _filter_field(
                        'Perfil',
                        dcc.Dropdown(
                            id=MANAGED_PROFILE_ID,
                            options=profile_options,
                            value='all',
                            clearable=False,
                        ),
                    ),
                    _filter_field(
                        'Estado',
                        dcc.Dropdown(
                            id=MANAGED_ENABLED_ID,
                            options=[
                                {'label': 'Todos', 'value': 'all'},
                                {'label': 'Activos', 'value': 'enabled'},
                                {'label': 'Desactivados', 'value': 'disabled'},
                            ],
                            value='all',
                            clearable=False,
                            searchable=False,
                        ),
                    ),
                ],
                className='atlanticus-users-admin__filters atlanticus-users-admin__filters--managed',
            ),
            html.Div(paged_list, id=MANAGED_LIST_ID),
        ],
        className='atlanticus-users-admin__section atlanticus-users-admin__view-section',
    )


def _promotion_row(
    candidate: dict[str, object],
    profiles: tuple[dict[str, object], ...],
    *,
    can_manage: bool,
) -> object:
    user = _candidate_identity(candidate)
    state = str(candidate.get('state') or '')
    conflict = state == 'conflict'
    default_profile = _default_profile(candidate, profiles)
    return html.Article(
        [
            _user_copy(user, candidate),
            html.Div(
                [
                    html.Span(
                        'Conflicto' if conflict else 'Promovible',
                        className=(
                            'atlanticus-users-admin__badge '
                            + (
                                'atlanticus-users-admin__badge--warning'
                                if conflict
                                else 'atlanticus-users-admin__badge--ready'
                            )
                        ),
                    ),
                    html.Label(
                        [
                            html.Span('Perfil a asignar'),
                            dcc.Dropdown(
                                id=candidate_profile_id(str(candidate.get('user_id'))),
                                options=[
                                    {
                                        'label': str(profile.get('label') or profile.get('key')),
                                        'value': profile.get('key'),
                                    }
                                    for profile in profiles
                                ],
                                value=default_profile,
                                clearable=False,
                                disabled=conflict or not can_manage,
                                className='atlanticus-users-admin__profile-select',
                            ),
                        ],
                        className='atlanticus-users-admin__candidate-profile-field',
                    ),
                    dbc.Button(
                        'Promover',
                        id=candidate_promote_id(str(candidate.get('user_id'))),
                        n_clicks=0,
                        color='primary',
                        size='sm',
                        disabled=conflict or not can_manage or default_profile is None,
                    ),
                ],
                className='atlanticus-users-admin__row-actions',
            ),
        ],
        className='atlanticus-users-admin__row',
    )


def _managed_row(candidate: dict[str, object], *, can_manage: bool) -> object:
    user = candidate.get('promoted_user')
    user = user if isinstance(user, dict) else {}
    enabled = user.get('enabled') is True
    return html.Article(
        [
            _user_copy(user, candidate),
            html.Div(
                [
                    html.Span(
                        'Activo' if enabled else 'Desactivado',
                        className=(
                            'atlanticus-users-admin__badge '
                            + (
                                'atlanticus-users-admin__badge--ready'
                                if enabled
                                else 'atlanticus-users-admin__badge--disabled'
                            )
                        ),
                    ),
                    html.Span(
                        str(user.get('profile_key') or '—'),
                        className='atlanticus-users-admin__profile-key',
                    ),
                    dbc.Button(
                        'Editar',
                        id=managed_edit_id(str(candidate.get('user_id'))),
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not can_manage,
                    ),
                ],
                className='atlanticus-users-admin__row-actions',
            ),
        ],
        className='atlanticus-users-admin__row',
    )


def _user_copy(user: dict[str, object], candidate: dict[str, object]) -> object:
    display_name = str(user.get('display_name') or user.get('email') or candidate.get('user_id'))
    email = user.get('email')
    issues = candidate.get('issues')
    issues = tuple(str(issue) for issue in issues) if isinstance(issues, list) else ()
    return html.Div(
        [
            html.Strong(display_name),
            html.Span(str(email or 'Sin email')),
            html.Code(str(candidate.get('user_id') or '')),
            html.Div(
                [html.Span(issue, className='atlanticus-users-admin__issue') for issue in issues],
                className='atlanticus-users-admin__issues',
            )
            if issues
            else None,
        ],
        className='atlanticus-users-admin__row-copy',
    )


def _paged_list(
    *,
    rows: tuple[object, ...],
    page: Page[object],
    rows_id: str,
    status_id: str,
    previous_id: str,
    next_id: str,
    page_size_id: str,
    page_id_factory: Callable[[int | str], object],
) -> object:
    rows_class = 'atlanticus-users-admin__rows'
    if page.total_count == 0:
        rows_class += ' atlanticus-users-admin__rows--empty'
    return html.Div(
        [
            html.Div(rows, id=rows_id, className=rows_class),
            _pagination(
                page=page,
                page_size_id=page_size_id,
                status_id=status_id,
                previous_id=previous_id,
                next_id=next_id,
                page_id_factory=page_id_factory,
            ),
        ],
        className='atlanticus-users-admin__paged-list',
        **{
            'data-page-size': str(page.request.page_size),
            'data-total-count': str(page.total_count),
        },
    )


def _pagination(
    *,
    page: Page[object],
    page_size_id: str,
    status_id: str,
    previous_id: str,
    next_id: str,
    page_id_factory: Callable[[int | str], object],
) -> object:
    return html.Div(
        [
            html.Div(
                page_status(page),
                id=status_id,
                className='atlanticus-users-admin__pagination-summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id=previous_id,
                        type='button',
                        disabled=not page.has_previous,
                        className='atlanticus-users-admin__pagination-button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *_page_buttons(page, page_id_factory),
                    html.Button(
                        '›',
                        id=next_id,
                        type='button',
                        disabled=not page.has_next,
                        className='atlanticus-users-admin__pagination-button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='atlanticus-users-admin__pagination-navigation',
            ),
            html.Label(
                [
                    html.Span('Filas', className='atlanticus-users-admin__pagination-page-size-label'),
                    html.Div(
                        dcc.Dropdown(
                            id=page_size_id,
                            options=[
                                {'label': str(size), 'value': size}
                                for size in ALLOWED_PAGE_SIZES
                            ],
                            value=page.request.page_size,
                            clearable=False,
                            searchable=False,
                        ),
                        className='atlanticus-users-admin__pagination-page-size',
                    ),
                ],
                className='atlanticus-users-admin__pagination-page-size-control',
            ),
        ],
        className='atlanticus-users-admin__pagination',
    )


def _page_buttons(
    page: Page[object],
    page_id_factory: Callable[[int | str], object],
) -> list[object]:
    buttons: list[object] = []
    for token in _pagination_tokens(page.request.page_number, page.page_count):
        if token is None:
            buttons.append(html.Span(
                    '…',
                    className='atlanticus-users-admin__pagination-ellipsis',
                    **{'aria-hidden': 'true'},
                ))
            continue
        active = token == page.request.page_number
        button_class = 'atlanticus-users-admin__pagination-button'
        if active:
            button_class += ' atlanticus-users-admin__pagination-button--active'
        buttons.append(
            html.Button(
                str(token),
                id=page_id_factory(token),
                type='button',
                n_clicks=0,
                disabled=active,
                className=button_class,
                **{'aria-label': f'Página {token}', 'aria-current': 'page' if active else 'false'},
            )
        )
    return buttons


def _pagination_tokens(current: int, page_count: int) -> tuple[int | None, ...]:
    if page_count <= 7:
        return tuple(range(1, page_count + 1))
    selected = {1, page_count, current}
    if current > 1:
        selected.add(current - 1)
    if current < page_count:
        selected.add(current + 1)
    ordered = sorted(selected)
    tokens: list[int | None] = []
    previous: int | None = None
    for value in ordered:
        if previous is not None and value - previous > 1:
            tokens.append(None)
        tokens.append(value)
        previous = value
    return tuple(tokens)


def _edit_modal(document: dict[str, object], *, can_manage: bool) -> object:
    profile_options = [
        {'label': str(profile.get('label') or profile.get('key')), 'value': profile.get('key')}
        for profile in _profiles(document)
    ]
    return html.Div(
        [
            html.Button(
                id=EDIT_BACKDROP_ID,
                n_clicks=0,
                type='button',
                className='atlanticus-users-admin__modal-backdrop',
                **{'aria-label': 'Cerrar editor de usuario'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.H2(id=EDIT_TITLE_ID),
                                    html.P(
                                        'La identidad es informativa. Solo el perfil y el estado '
                                        'pueden modificarse.',
                                    ),
                                ],
                                className='atlanticus-users-admin__modal-heading',
                            ),
                            html.Button(
                                id=EDIT_CLOSE_ID,
                                n_clicks=0,
                                type='button',
                                className='btn-close',
                                **{'aria-label': 'Cerrar editor de usuario'},
                            ),
                        ],
                        className='modal-header atlanticus-users-admin__modal-header',
                    ),
                    html.Div(
                        [
                            html.Div(id=EDIT_IDENTITY_ID),
                            _field(
                                'Perfil',
                                dcc.Dropdown(
                                    id=EDIT_PROFILE_ID,
                                    options=profile_options,
                                    clearable=False,
                                    disabled=not can_manage,
                                ),
                            ),
                            dbc.Checklist(
                                id=EDIT_ENABLED_ID,
                                options=[
                                    {
                                        'label': 'Usuario activo',
                                        'value': 'enabled',
                                        'disabled': not can_manage,
                                    }
                                ],
                                value=[],
                                switch=True,
                            ),
                            html.Div(id=EDIT_RESULT_ID),
                        ],
                        className='modal-body atlanticus-users-admin__modal-body',
                    ),
                    html.Footer(
                        [
                            dbc.Button(
                                'Cancelar',
                                id=EDIT_CANCEL_ID,
                                n_clicks=0,
                                color='secondary',
                                outline=True,
                            ),
                            dbc.Button(
                                'Guardar',
                                id=EDIT_SAVE_ID,
                                n_clicks=0,
                                color='primary',
                                disabled=not can_manage,
                            ),
                        ],
                        className='modal-footer atlanticus-users-admin__modal-actions',
                    ),
                ],
                className='modal-content atlanticus-users-admin__modal-card',
            ),
        ],
        id=EDIT_MODAL_ID,
        className='atlanticus-users-admin__modal',
    )


def _section_header(title: str, description: str) -> object:
    return html.Div(
        [html.H3(title), html.P(description)],
        className='atlanticus-users-admin__section-copy',
    )


def _filter_field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label), control],
        className='atlanticus-users-admin__filter-field',
    )


def _field(label: str, control: object) -> object:
    return html.Label([html.Span(label), control], className='atlanticus-users-admin__field')


def _identity_item(label: str, value: object) -> object:
    return html.Div(
        [html.Span(label), html.Strong(str(value) if value not in (None, '') else '—')],
        className='atlanticus-users-admin__identity-item',
    )


def _empty_state(*, title: str, copy: str) -> object:
    return html.Div(
        [
            html.Span('•', className='atlanticus-users-admin__empty-icon', **{'aria-hidden': 'true'}),
            html.Strong(title),
            html.Span(copy),
        ],
        className='atlanticus-users-admin__empty-state',
        role='status',
    )


def _profiles(document: dict[str, object] | None) -> tuple[dict[str, object], ...]:
    if not isinstance(document, dict):
        return ()
    profiles = document.get('profiles')
    if not isinstance(profiles, list):
        return ()
    return tuple(profile for profile in profiles if isinstance(profile, dict))


def _candidates(document: dict[str, object] | None) -> tuple[dict[str, object], ...]:
    if not isinstance(document, dict):
        return ()
    candidates = document.get('candidates')
    if not isinstance(candidates, list):
        return ()
    return tuple(candidate for candidate in candidates if isinstance(candidate, dict))


def _candidate_identity(candidate: dict[str, object]) -> dict[str, object]:
    for key in ('directory_user', 'registry_user', 'promoted_user'):
        value = candidate.get(key)
        if isinstance(value, dict):
            return value
    return {'user_id': candidate.get('user_id')}


def _matches_search(candidate: dict[str, object], query: str | None) -> bool:
    normalized = (query or '').strip().casefold()
    if not normalized:
        return True
    values: list[str] = [str(candidate.get('user_id') or '')]
    for key in ('registry_user', 'directory_user', 'promoted_user'):
        user = candidate.get(key)
        if isinstance(user, dict):
            values.extend(
                str(user.get(field) or '')
                for field in ('display_name', 'email', 'subject_id', 'issuer')
            )
    return any(normalized in value.casefold() for value in values)


def _matches_managed_profile(candidate: dict[str, object], profile_filter: str | None) -> bool:
    if profile_filter in (None, '', 'all'):
        return True
    user = candidate.get('promoted_user')
    return isinstance(user, dict) and user.get('profile_key') == profile_filter


def _matches_enabled(candidate: dict[str, object], enabled_filter: str | None) -> bool:
    if enabled_filter in (None, '', 'all'):
        return True
    user = candidate.get('promoted_user')
    if not isinstance(user, dict):
        return False
    enabled = user.get('enabled') is True
    return enabled if enabled_filter == 'enabled' else not enabled


def _default_profile(
    candidate: dict[str, object],
    profiles: tuple[dict[str, object], ...],
) -> str | None:
    available = {str(profile.get('key')) for profile in profiles if profile.get('key') is not None}
    registry_user = candidate.get('registry_user')
    if isinstance(registry_user, dict):
        configured = registry_user.get('profile_key')
        if isinstance(configured, str) and configured in available:
            return configured
    if 'basic' in available:
        return 'basic'
    return next(iter(available), None)
