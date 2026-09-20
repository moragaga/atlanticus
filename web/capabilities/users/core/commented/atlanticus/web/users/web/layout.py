# Espejo pedagógico: Users Administration conserva identidad de origen y limita edición a profile y enabled.
from __future__ import annotations

from dash import dcc, html
import dash_bootstrap_components as dbc

from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, DEFAULT_PAGE_SIZE, PageRequest, paginate_items
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
from atlanticus.web.users.web.models import UsersAdminWebContext
from atlanticus.web.users.web.serialization import snapshot_to_document


def build_users_admin_configuration(context: UsersAdminWebContext) -> object:
    try:
        snapshot = snapshot_to_document(context.administration.discover())
        error = None
    except Exception:
        snapshot = {'registry_version': None, 'profiles': [], 'candidates': []}
        error = 'No fue posible cargar Users Administration.'
    return html.Div(
        [
            dcc.Store(id=SNAPSHOT_ID, data=snapshot, storage_type='memory'),
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
                                        'Verifica identidades, promueve usuarios y controla perfil y estado.'
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
            _promotion_section(snapshot, can_manage=context.can_manage()),
            _managed_section(snapshot, can_manage=context.can_manage()),
            _edit_modal(snapshot, can_manage=context.can_manage()),
        ],
        className='atlanticus-users-admin',
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
    return rows or (_empty('No hay usuarios pendientes para los filtros seleccionados.'),), page


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
    return rows or (_empty('No hay usuarios administrados para los filtros seleccionados.'),), page


def page_status(page) -> str:
    if page.total_count == 0:
        return '0 de 0'
    return f'{page.start_index}–{page.end_index} de {page.total_count}'


def identity_details(user: dict[str, object] | None) -> object:
    if not isinstance(user, dict):
        return html.Div('Identidad no disponible.', className='atlanticus-users-admin__empty')
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
    rows, page = render_promotion_rows(
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
                    dbc.Input(
                        id=PROMOTION_SEARCH_ID,
                        type='search',
                        placeholder='Buscar nombre, email o identidad',
                    ),
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
                ],
                className='atlanticus-users-admin__filters',
            ),
            html.Div(rows, id=PROMOTION_ROWS_ID, className='atlanticus-users-admin__rows'),
            _pagination(
                page=page,
                page_size_id=PROMOTION_PAGE_SIZE_ID,
                status_id=PROMOTION_STATUS_ID,
                previous_id=PROMOTION_PREVIOUS_ID,
                next_id=PROMOTION_NEXT_ID,
            ),
            html.Div(id=PROMOTION_RESULT_ID),
        ],
        className='atlanticus-users-admin__section',
    )


def _managed_section(document: dict[str, object], *, can_manage: bool) -> object:
    rows, page = render_managed_rows(
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
                'Usuarios promovidos. La identidad es informativa; solo profile y estado son editables.',
            ),
            html.Div(
                [
                    dbc.Input(
                        id=MANAGED_SEARCH_ID,
                        type='search',
                        placeholder='Buscar nombre, email o identidad',
                    ),
                    dcc.Dropdown(
                        id=MANAGED_PROFILE_ID,
                        options=profile_options,
                        value='all',
                        clearable=False,
                    ),
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
                ],
                className='atlanticus-users-admin__filters atlanticus-users-admin__filters--managed',
            ),
            html.Div(rows, id=MANAGED_ROWS_ID, className='atlanticus-users-admin__rows'),
            _pagination(
                page=page,
                page_size_id=MANAGED_PAGE_SIZE_ID,
                status_id=MANAGED_STATUS_ID,
                previous_id=MANAGED_PREVIOUS_ID,
                next_id=MANAGED_NEXT_ID,
            ),
        ],
        className='atlanticus-users-admin__section',
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
                            + ('atlanticus-users-admin__badge--warning' if conflict else 'atlanticus-users-admin__badge--ready')
                        ),
                    ),
                    dcc.Dropdown(
                        id=candidate_profile_id(str(candidate.get('user_id'))),
                        options=[
                            {'label': str(profile.get('label') or profile.get('key')), 'value': profile.get('key')}
                            for profile in profiles
                        ],
                        value=default_profile,
                        clearable=False,
                        disabled=conflict or not can_manage,
                        className='atlanticus-users-admin__profile-select',
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
                            + ('atlanticus-users-admin__badge--ready' if enabled else 'atlanticus-users-admin__badge--disabled')
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


def _pagination(*, page, page_size_id, status_id, previous_id, next_id) -> object:
    return html.Div(
        [
            html.Div(
                [
                    html.Span('Filas'),
                    dcc.Dropdown(
                        id=page_size_id,
                        options=[{'label': str(size), 'value': size} for size in ALLOWED_PAGE_SIZES],
                        value=page.request.page_size,
                        clearable=False,
                        searchable=False,
                        className='atlanticus-users-admin__page-size',
                    ),
                ],
                className='atlanticus-users-admin__page-size-control',
            ),
            html.Span(page_status(page), id=status_id),
            html.Div(
                [
                    dbc.Button(
                        'Anterior',
                        id=previous_id,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not page.has_previous,
                    ),
                    dbc.Button(
                        'Siguiente',
                        id=next_id,
                        n_clicks=0,
                        color='secondary',
                        outline=True,
                        size='sm',
                        disabled=not page.has_next,
                    ),
                ],
                className='atlanticus-users-admin__page-actions',
            ),
        ],
        className='atlanticus-users-admin__pagination',
    )


def _edit_modal(document: dict[str, object], *, can_manage: bool) -> object:
    profile_options = [
        {'label': str(profile.get('label') or profile.get('key')), 'value': profile.get('key')}
        for profile in _profiles(document)
    ]
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle(id=EDIT_TITLE_ID), close_button=False),
            dbc.ModalBody(
                [
                    html.Div(id=EDIT_IDENTITY_ID),
                    _field(
                        'Profile',
                        dcc.Dropdown(
                            id=EDIT_PROFILE_ID,
                            options=profile_options,
                            clearable=False,
                            disabled=not can_manage,
                        ),
                    ),
                    dbc.Checklist(
                        id=EDIT_ENABLED_ID,
                        options=[{'label': 'Usuario activo', 'value': 'enabled'}],
                        value=[],
                        switch=True,
                        disabled=not can_manage,
                    ),
                    html.Div(id=EDIT_RESULT_ID),
                ],
                className='atlanticus-users-admin__modal-body',
            ),
            dbc.ModalFooter(
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
                ]
            ),
        ],
        id=EDIT_MODAL_ID,
        is_open=False,
    )


def _section_header(title: str, description: str) -> object:
    return html.Div(
        [html.H3(title), html.P(description)],
        className='atlanticus-users-admin__section-copy',
    )


def _field(label: str, control: object) -> object:
    return html.Label([html.Span(label), control], className='atlanticus-users-admin__field')


def _identity_item(label: str, value: object) -> object:
    return html.Div(
        [html.Span(label), html.Strong(str(value) if value not in (None, '') else '—')],
        className='atlanticus-users-admin__identity-item',
    )


def _empty(message: str) -> object:
    return html.Div(message, className='atlanticus-users-admin__empty')


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
