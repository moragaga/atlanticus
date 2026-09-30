from __future__ import annotations

from typing import TYPE_CHECKING

import dash_bootstrap_components as dbc
from dash import dcc, html

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.operational.identification import (
    OperationalCatalog,
    Position,
    assignment_source_key,
)
from atlanticus.web.pagination import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    Page,
    PageRequest,
    paginate_items,
)
from atlanticus.web.projection.models import ProjectionAlignment, ProjectionStatus
from atlanticus.web.source.models import SourceSnapshot

if TYPE_CHECKING:
    from ada.web.application.configuration_manager.operational import (
        OperationalAssignmentContext,
        OperationalCatalogManagerWebContext,
    )


def build_operational_catalog_configuration(
    context: OperationalCatalogManagerWebContext,
) -> object:
    if not context.can_manage():
        return html.P('You do not have access to this configuration.')
    try:
        payload = context.current_payload_provider()
        catalog = (
            OperationalCatalog.from_document(payload)
            if payload is not None
            else OperationalCatalog()
        )
        position_list, position_page = render_position_list(
            catalog,
            None,
            1,
            DEFAULT_PAGE_SIZE,
        )
    except Exception:
        return html.P('Operational catalog could not be loaded.')
    return html.Div(
        [
            dcc.Store(id=ids.CATALOG_EDITOR, data=catalog.to_document()),
            dcc.Store(id=ids.POSITION_PAGE, data=1),
            dcc.Store(id=ids.POSITION_CURRENT_PAGE, data=position_page.request.page_number),
            dcc.Dropdown(
                id=ids.POSITION_SELECT,
                options=_position_options(catalog, include_inactive=True),
                style={'display': 'none'},
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3('Catálogo de cargos'),
                                    html.P(
                                        'Los identificadores se generan una sola vez y son '
                                        'inmutables. '
                                        'Los cargos dejan de utilizarse desactivándolos.'
                                    ),
                                ],
                                className='ada-operational-admin__section-copy',
                            ),
                            html.Button(
                                'Nuevo cargo',
                                id=ids.POSITION_NEW,
                                n_clicks=0,
                                type='button',
                                className='btn btn-outline-secondary',
                            ),
                        ],
                        className='ada-operational-admin__section-head',
                    ),
                    html.Div(
                        [
                            _metadata_cell('Áreas operacionales', 'Mina · Planta'),
                            _metadata_cell('Grupos', '1 · 2 · 3 · 4'),
                        ],
                        className='ada-operational-admin__metadata',
                    ),
                    _filter_bar(ids.POSITION_SEARCH, 'Buscar cargos'),
                    _list_shell(ids.POSITION_LIST, position_list, ids.POSITION_SIZE),
                    html.Div(
                        page_label(position_page),
                        id=ids.POSITION_STATUS,
                        className='ada-operational-admin__sr-only',
                        **{'aria-live': 'polite'},
                    ),
                ],
                className='ada-operational-admin__catalog-section',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H3('Borrador local · catálogo de cargos'),
                                    html.P(
                                        'Guarda el catálogo actual en este navegador. '
                                        'Validar, publicar y proyectar se realiza en Estado y '
                                        'trazabilidad.'
                                    ),
                                ],
                                className='ada-operational-admin__section-copy',
                            ),
                            html.Button(
                                'Guardar borrador',
                                id=ids.CATALOG_SAVE_DRAFT,
                                n_clicks=0,
                                type='button',
                                className='btn btn-primary',
                            ),
                        ],
                        className='ada-operational-admin__section-head',
                    ),
                    html.Div(id=ids.CATALOG_SAVE_RESULT, role='status'),
                ],
                className='ada-operational-admin__catalog-section',
            ),
            _position_modal(),
        ],
        className='ada-operational-admin atlanticus-bootstrap',
    )


def build_operational_assignments(context: OperationalAssignmentContext) -> object:
    if not context.can_manage():
        return html.P('You do not have access to this configuration.')
    try:
        assignment_list, assignment_page = render_assignment_list(
            context,
            None,
            1,
            DEFAULT_PAGE_SIZE,
        )
        projected_catalog = context.service.catalog_for_read()
    except Exception:
        return html.P('Operational assignments could not be loaded.')
    return html.Div(
        [
            dcc.Store(id=ids.ASSIGN_PAGE, data=1),
            dcc.Store(id=ids.ASSIGN_CURRENT_PAGE, data=assignment_page.request.page_number),
            dcc.Store(id=ids.USER),
            dcc.Store(id=ids.ASSIGNMENT_REVISION),
            html.Section(
                [
                    html.Div(
                        [
                            html.H3('Asignaciones'),
                            html.P('Información operacional de usuarios promovidos.'),
                        ],
                        className='ada-operational-admin__section-copy',
                    ),
                    html.Div(id=ids.ASSIGN_FEEDBACK, role='status'),
                    _filter_bar(ids.ASSIGN_SEARCH, 'Buscar usuarios'),
                    _list_shell(ids.ASSIGN_LIST, assignment_list, ids.ASSIGN_SIZE),
                    html.Div(
                        page_label(assignment_page),
                        id=ids.ASSIGN_STATUS,
                        className='ada-operational-admin__sr-only',
                        **{'aria-live': 'polite'},
                    ),
                ],
                className='ada-operational-admin__catalog-section',
            ),
            _assignment_modal(projected_catalog),
        ],
        className='ada-operational-admin atlanticus-bootstrap',
    )


def build_operational_catalog_history_preview(payload: dict[str, object]) -> object:
    catalog = OperationalCatalog.from_document(payload)
    return html.Div(
        [
            html.H4('Catálogo de cargos'),
            html.Div(
                [
                    _history_item('Cargos configurados', str(len(catalog.positions))),
                    _history_item(
                        'Cargos activos',
                        str(sum(position.active for position in catalog.positions)),
                    ),
                ]
            ),
        ]
    )


def render_assignment_list(
    context: OperationalAssignmentContext,
    query: str | None,
    number: int,
    size: int,
) -> tuple[object, Page[object]]:
    users = tuple(
        sorted(
            context.promoted_users(),
            key=lambda user: (
                user.display_name.casefold(),
                user.user_id,
            ),
        )
    )
    needle = (query or '').strip().casefold()
    filtered = tuple(
        user
        for user in users
        if not needle
        or any(
            needle in str(value or '').casefold()
            for value in (user.display_name, getattr(user, 'email', None), user.user_id)
        )
    )
    page = paginate_items(filtered, PageRequest(number, size))
    try:
        catalog = context.service.catalog_for_read()
        labels = {item.id: item.label for item in catalog.positions}
    except Exception:
        labels = {}
    rows = tuple(_assignment_row(context, user, labels) for user in page.items)
    return _paged_list(
        rows=rows,
        page=page,
        prev_id=ids.ASSIGN_PREVIOUS,
        next_id=ids.ASSIGN_NEXT,
        jump_type=ids.ASSIGN_JUMP,
        empty='No hay usuarios promovidos que coincidan con la búsqueda.',
    ), page


def render_position_list(
    catalog: OperationalCatalog,
    query: str | None,
    number: int,
    size: int,
) -> tuple[object, Page[Position]]:
    needle = (query or '').strip().casefold()
    positions = tuple(
        position
        for position in sorted(
            catalog.positions,
            key=lambda item: (
                item.label.casefold(),
                item.id,
            ),
        )
        if not needle or needle in position.label.casefold() or needle in position.id.casefold()
    )
    page = paginate_items(positions, PageRequest(number, size))
    return _paged_list(
        rows=tuple(_position_row(position) for position in page.items),
        page=page,
        prev_id=ids.POSITION_PREVIOUS,
        next_id=ids.POSITION_NEXT,
        jump_type=ids.POSITION_JUMP,
        empty='No hay cargos que coincidan con la búsqueda.',
    ), page


def _assignment_row(
    context: OperationalAssignmentContext,
    user: object,
    positions: dict[str, str],
) -> object:
    user_id = user.user_id
    try:
        snapshot, assignment = context.service.assignment_for_edit(user_id)
        status = context.service.projection_status(assignment_source_key(user_id))
        state = _status_label(status)
        publication_exists = snapshot.current is not None
        assignment_label = (
            'Sin asignación'
            if not publication_exists
            else 'Con atributos'
            if any(
                value is not None
                for value in (assignment.area_id, assignment.position_id, assignment.group_id)
            )
            else 'Publicada sin atributos'
        )
        details = (
            'Sin información operacional publicada'
            if not publication_exists
            else ' · '.join(
                (
                    f'Área: {dict(mina="Mina", planta="Planta").get(assignment.area_id, "—")}',
                    'Cargo: '
                    f'{positions.get(assignment.position_id, assignment.position_id or "—")}',
                    f'Grupo: {assignment.group_id if assignment.group_id is not None else "—"}',
                )
            )
        )
    except Exception:
        state = 'Datos no disponibles'
        assignment_label = 'No verificable'
        details = 'Source and Projection could not be verified.'
    return html.Article(
        [
            html.Div(
                [
                    html.Strong(user.display_name),
                    html.Span(getattr(user, 'email', None) or user.user_id),
                    html.Small(details),
                ],
                className='ada-operational-admin__row-copy',
            ),
            html.Div(
                [
                    html.Span(assignment_label, className='ada-operational-admin__badge'),
                    html.Span(state, className='ada-operational-admin__badge'),
                    html.Button(
                        'Editar',
                        id={'type': ids.ASSIGN_EDIT, 'index': user_id},
                        n_clicks=0,
                        type='button',
                        className='btn btn-outline-secondary btn-sm',
                    ),
                ],
                className='ada-operational-admin__row-actions',
            ),
        ],
        className='ada-operational-admin__row',
    )


def _position_row(position: Position) -> object:
    return html.Article(
        [
            html.Div(
                [html.Strong(position.label), html.Code(position.id)],
                className='ada-operational-admin__row-copy',
            ),
            html.Div(
                [
                    html.Span(
                        'Activo' if position.active else 'Inactivo',
                        className='ada-operational-admin__badge',
                    ),
                    html.Button(
                        'Editar',
                        id={'type': ids.POSITION_EDIT, 'index': position.id},
                        n_clicks=0,
                        type='button',
                        className='btn btn-outline-secondary btn-sm',
                    ),
                ],
                className='ada-operational-admin__row-actions',
            ),
        ],
        className='ada-operational-admin__row',
    )


def _list_shell(list_id: str, initial: object, size_id: str) -> object:
    return html.Div(
        [
            html.Div(initial, id=list_id, className='ada-operational-admin__list-view'),
            html.Label(
                [
                    html.Span('Filas'),
                    _dropdown(
                        size_id,
                        [{'label': str(size), 'value': size} for size in ALLOWED_PAGE_SIZES],
                        value=DEFAULT_PAGE_SIZE,
                        clearable=False,
                    ),
                ],
                className='ada-operational-admin__footer-size',
            ),
        ],
        className='ada-operational-admin__list-shell',
    )


def _paged_list(
    *,
    rows: tuple[object, ...],
    page: Page[object],
    prev_id: str,
    next_id: str,
    jump_type: str,
    empty: str,
) -> object:
    buttons = tuple(
        html.Span('…', className='ada-operational-admin__pager-ellipsis')
        if number is None
        else html.Button(
            str(number),
            id={'type': jump_type, 'index': number},
            type='button',
            n_clicks=0,
            disabled=number == page.request.page_number,
            className=(
                'ada-operational-admin__pager-button ada-operational-admin__pager-button--active'
                if number == page.request.page_number
                else 'ada-operational-admin__pager-button'
            ),
        )
        for number in _page_tokens(page.request.page_number, page.page_count)
    )
    return html.Div(
        [
            html.Div(
                rows or (html.Div(empty, className='ada-operational-admin__empty'),),
                className='ada-operational-admin__rows',
            ),
            html.Div(
                [
                    html.Span(
                        f'Mostrando {page_label(page)}',
                        className='ada-operational-admin__page-summary',
                    ),
                    html.Div(
                        [
                            html.Button(
                                '‹',
                                id=prev_id,
                                n_clicks=0,
                                type='button',
                                disabled=not page.has_previous,
                                className='ada-operational-admin__pager-button',
                                **{'aria-label': 'Página anterior'},
                            ),
                            *buttons,
                            html.Button(
                                '›',
                                id=next_id,
                                n_clicks=0,
                                type='button',
                                disabled=not page.has_next,
                                className='ada-operational-admin__pager-button',
                                **{'aria-label': 'Página siguiente'},
                            ),
                        ],
                        className='ada-operational-admin__pager',
                    ),
                ],
                className='ada-operational-admin__pagination',
            ),
        ],
        className='ada-operational-admin__paged-list',
        **{
            'data-page-size': str(page.request.page_size),
            'data-empty': 'true' if not rows else 'false',
        },
    )


def _page_tokens(current: int, total: int) -> tuple[int | None, ...]:
    if total <= 7:
        return tuple(range(1, total + 1))
    values = sorted({1, total, *(range(max(1, current - 2), min(total, current + 2) + 1))})
    result: list[int | None] = []
    for value in values:
        if result and result[-1] is not None and value > result[-1] + 1:
            result.append(None)
        result.append(value)
    return tuple(result)


def page_label(page: Page[object]) -> str:
    if not page.total_count:
        return '0 de 0'
    return f'{page.start_index}–{page.end_index} de {page.total_count}'


def _filter_bar(search_id: str, label: str) -> object:
    return html.Div(
        [
            html.Label(
                [
                    html.Span(label),
                    dcc.Input(id=search_id, type='search', debounce=True, className='form-control'),
                ],
                className='ada-operational-admin__field',
            ),
        ],
        className='ada-operational-admin__filters',
    )


def _assignment_modal(catalog: OperationalCatalog) -> object:
    return _modal(
        ids.ASSIGN_MODAL,
        ids.ASSIGN_MODAL_BACKDROP,
        ids.ASSIGN_MODAL_CLOSE,
        'Editar asignación',
        [
            html.P(id=ids.ASSIGN_SELECTED_NAME, className='ada-operational-admin__modal-copy'),
            html.Div(id=ids.ASSIGN_MODAL_STATUS, className='ada-operational-admin__modal-copy'),
            _field(
                'Área',
                _dropdown(
                    ids.AREA,
                    [{'label': 'Mina', 'value': 'mina'}, {'label': 'Planta', 'value': 'planta'}],
                    placeholder='Sin información',
                ),
            ),
            _field(
                'Cargo',
                _dropdown(
                    ids.POSITION,
                    _position_options(catalog),
                    placeholder='Sin información',
                ),
            ),
            _field(
                'Grupo',
                _dropdown(
                    ids.GROUP,
                    [{'label': f'Grupo {number}', 'value': number} for number in range(1, 5)],
                    placeholder='Sin información',
                ),
            ),
            html.Div(id=ids.ASSIGNMENT_RESULT, role='status'),
        ],
        [
            html.Button(
                'Cancelar',
                id=ids.ASSIGN_MODAL_CANCEL,
                n_clicks=0,
                type='button',
                className='btn btn-outline-secondary',
            ),
            html.Button(
                'Reintentar proyección',
                id=ids.ASSIGNMENT_REPROJECT,
                type='button',
                n_clicks=0,
                className='btn btn-outline-secondary',
            ),
            html.Button(
                'Guardar asignación',
                id=ids.ASSIGNMENT_SAVE,
                n_clicks=0,
                type='button',
                className='btn btn-primary',
            ),
        ],
    )


def _position_modal() -> object:
    return _modal(
        ids.POSITION_MODAL,
        ids.POSITION_MODAL_BACKDROP,
        ids.POSITION_MODAL_CLOSE,
        'Cargo',
        [
            html.Div(
                [
                    html.Span('Identificador', className='ada-operational-admin__identifier-label'),
                    html.Code(
                        'Se generará al guardar',
                        id=ids.POSITION_ID,
                        className='ada-operational-admin__identifier-value',
                    ),
                ],
                className='ada-operational-admin__identifier',
            ),
            _field(
                'Nombre del cargo',
                dbc.Input(
                    id=ids.POSITION_LABEL,
                    type='text',
                    maxLength=120,
                    className='form-control',
                ),
            ),
            dbc.Checklist(
                id=ids.POSITION_ACTIVE,
                options=[{'label': 'Activo', 'value': 'active'}],
                value=['active'],
                className='ada-operational-admin__check',
            ),
            html.Div(id=ids.POSITION_RESULT, role='status'),
        ],
        [
            html.Button(
                'Cancelar',
                id=ids.POSITION_MODAL_CANCEL,
                type='button',
                n_clicks=0,
                className='btn btn-outline-secondary',
            ),
            html.Button(
                'Guardar en borrador',
                id=ids.POSITION_APPLY,
                n_clicks=0,
                type='button',
                className='btn btn-primary',
            ),
        ],
    )


def _modal(
    modal_id: str,
    backdrop_id: str,
    close_id: str,
    title: str,
    body: list[object],
    actions: list[object],
) -> object:
    return html.Div(
        [
            html.Button(
                id=backdrop_id,
                type='button',
                n_clicks=0,
                className='ada-operational-admin__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Section(
                [
                    html.Header(
                        [
                            html.Div(
                                [
                                    html.H2(title),
                                    html.P('Revisa la información antes de guardar.'),
                                ],
                                className='ada-operational-admin__modal-heading',
                            ),
                            html.Button(
                                '×',
                                id=close_id,
                                type='button',
                                n_clicks=0,
                                className='ada-operational-admin__modal-close',
                                **{'aria-label': 'Cerrar formulario'},
                            ),
                        ],
                        className='ada-operational-admin__modal-header',
                    ),
                    html.Div(body, className='ada-operational-admin__modal-body'),
                    html.Footer(actions, className='ada-operational-admin__modal-actions'),
                ],
                className='ada-operational-admin__modal-card',
                role='dialog',
                **{'aria-modal': 'true', 'aria-label': title},
            ),
        ],
        id=modal_id,
        className=modal_class(False),
    )


def _field(label: str, control: object) -> object:
    return html.Label(
        [html.Span(label), control],
        className='ada-operational-admin__field',
    )


def _dropdown(component_id: str, options: list[dict], **kwargs: object) -> object:
    return dcc.Dropdown(
        id=component_id,
        options=options,
        className='ada-operational-admin__select',
        style=_dash_select_style(),
        **kwargs,
    )


def _dash_select_style() -> dict[str, str]:
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


def _revision(snapshot: SourceSnapshot) -> str | None:
    return snapshot.current.release_ref.release_id.value if snapshot.current else None


def _position_options(
    catalog: OperationalCatalog,
    *,
    include_inactive: bool = False,
) -> list[dict[str, object]]:
    return [
        {
            'label': item.label,
            'value': item.id,
            'disabled': not item.active and not include_inactive,
        }
        for item in catalog.positions
    ]


def _release_label(release: object) -> str:
    return 'Sin publicación' if release is None else release.release_id.value


def _status_label(status: ProjectionStatus) -> str:
    if status.source_current_release is None:
        return 'Sin publicar' if status.projected_source_release is None else 'Source ausente'
    if status.alignment is ProjectionAlignment.CURRENT:
        return 'Sincronizado'
    if status.alignment is ProjectionAlignment.NEVER_PROJECTED:
        return 'Pendiente de proyección'
    return 'Proyección desactualizada'


def _metadata_cell(label: str, value: str) -> object:
    return html.Div(
        [html.Span(label), html.Code(value)],
        className='ada-operational-admin__metadata-cell',
    )


def _history_item(label: str, value: str) -> object:
    return html.Div([html.Small(label), html.Strong(value)])


def modal_class(opened: bool) -> str:
    base = 'ada-operational-admin__modal'
    return f'{base} {base}--open' if opened else base
