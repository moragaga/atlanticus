from __future__ import annotations

from typing import TYPE_CHECKING

from dash import dcc, html

from ada.web.application.configuration_manager import operational_ids as ids
from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
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
    from ada.web.application.configuration_manager.operational import OperationalManagerContext


def build_operational_manager_layout(context: OperationalManagerContext) -> object:
    if not context.can_manage():
        return html.P('No tienes acceso a esta configuración.')
    try:
        snapshot, catalog = context.service.catalog_for_edit()
        assignment_list, assignment_page = render_assignment_list(
            context, None, 1, DEFAULT_PAGE_SIZE
        )
        position_list, position_page = render_position_list(context, None, 1, DEFAULT_PAGE_SIZE)
        metadata = catalog_metadata(context, snapshot)
        projected_catalog = context.service.catalog_for_read()
    except Exception:
        return html.P('No fue posible cargar los datos operacionales.')
    return html.Div(
        [
            dcc.Store(id=ids.SURFACE, data='configuration'),
            dcc.Store(id=ids.VIEW, data='assignments'),
            dcc.Store(id=ids.ASSIGN_PAGE, data=1),
            dcc.Store(id=ids.ASSIGN_CURRENT_PAGE, data=assignment_page.request.page_number),
            dcc.Store(id=ids.POSITION_PAGE, data=1),
            dcc.Store(id=ids.POSITION_CURRENT_PAGE, data=position_page.request.page_number),
            dcc.Store(id=ids.USER),
            dcc.Store(id=ids.ASSIGNMENT_REVISION),
            dcc.Store(id=ids.CATALOG_REVISION, data=_revision(snapshot)),
            dcc.Dropdown(
                id=ids.POSITION_SELECT,
                options=_position_options(catalog, include_inactive=True),
                style={'display': 'none'},
            ),
            html.Div(
                [
                    html.Button(
                        'Configuración',
                        id=ids.CONFIG_TAB,
                        n_clicks=0,
                        type='button',
                        role='tab',
                        className=_surface_tab_class(True),
                        **{'aria-selected': 'true'},
                    ),
                    html.Button(
                        'Estado y trazabilidad',
                        id=ids.TRACE_TAB,
                        n_clicks=0,
                        type='button',
                        role='tab',
                        className=_surface_tab_class(False),
                        **{'aria-selected': 'false'},
                    ),
                ],
                className='ada-operational-admin__primary-tabs',
                role='tablist',
            ),
            html.Div(
                [
                    html.Div(
                        [
                            _provider_label('Fuente de verdad', context.source_name),
                            _provider_label('Proyección', context.projection_name),
                        ],
                        className='ada-operational-admin__providers',
                    ),
                    html.Div(
                        [
                            html.Button(
                                'Asignaciones',
                                id=ids.ASSIGN_TAB,
                                n_clicks=0,
                                className=_tab_class(True),
                                type='button',
                                role='tab',
                                **{'aria-selected': 'true'},
                            ),
                            html.Button(
                                'Cargos',
                                id=ids.POSITION_TAB,
                                n_clicks=0,
                                className=_tab_class(False),
                                type='button',
                                role='tab',
                                **{'aria-selected': 'false'},
                            ),
                        ],
                        className='ada-operational-admin__tabs',
                        role='tablist',
                    ),
                    html.Div(
                        [
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H3('Asignaciones'),
                                                    html.P(
                                                        'Información operacional de usuarios promovidos.'
                                                    ),
                                                ],
                                                className='ada-operational-admin__section-copy',
                                            ),
                                        ],
                                        className='ada-operational-admin__section-head',
                                    ),
                                    _filter_bar(ids.ASSIGN_SEARCH, 'Buscar usuarios'),
                                    _list_shell(ids.ASSIGN_LIST, assignment_list, ids.ASSIGN_SIZE),
                                    html.Div(
                                        page_label(assignment_page),
                                        id=ids.ASSIGN_STATUS,
                                        className='ada-operational-admin__sr-only',
                                        **{'aria-live': 'polite'},
                                    ),
                                ],
                                id=ids.ASSIGN_PANEL,
                                className=_panel_class(True),
                                role='tabpanel',
                            ),
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H3('Catálogo de cargos'),
                                                    html.P(
                                                        'Identificadores automáticos e inmutables. Desactiva los cargos que ya no se usan.'
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
                                    _list_shell(
                                        ids.POSITION_LIST, position_list, ids.POSITION_SIZE
                                    ),
                                    html.Div(
                                        page_label(position_page),
                                        id=ids.POSITION_STATUS,
                                        className='ada-operational-admin__sr-only',
                                        **{'aria-live': 'polite'},
                                    ),
                                ],
                                id=ids.POSITION_PANEL,
                                className=_panel_class(False),
                                role='tabpanel',
                            ),
                        ],
                        className='ada-operational-admin__body',
                    ),
                ],
                id=ids.CONFIG_PANEL,
                className=_surface_class(True),
                role='tabpanel',
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H3('Catálogo de cargos'),
                            html.P(
                                'Revisiones efectivamente publicadas y proyectadas. El catálogo y cada usuario tienen Source independientes.'
                            ),
                        ],
                        className='ada-operational-admin__section-copy',
                    ),
                    html.Div(metadata, id=ids.CATALOG_METADATA),
                    html.Div(
                        [
                            html.P(
                                'Si existe una publicación pendiente, puedes reintentar su proyección sin modificar el Source.',
                                className='ada-operational-admin__trace-copy',
                            ),
                            html.Button(
                                'Reintentar proyección',
                                id=ids.CATALOG_REPROJECT,
                                n_clicks=0,
                                type='button',
                                className='btn btn-outline-secondary btn-sm',
                            ),
                        ],
                        className='ada-operational-admin__trace-actions',
                    ),
                    html.Div(
                        id=ids.TRACE_FEEDBACK,
                        className='ada-operational-admin__trace-feedback',
                        role='status',
                    ),
                    html.P(
                        'Las asignaciones son individuales: su estado y su reintento se consultan en cada usuario de la pestaña Asignaciones.',
                        className='ada-operational-admin__trace-copy',
                    ),
                ],
                id=ids.TRACE_PANEL,
                className=_surface_class(False),
                role='tabpanel',
            ),
            _assignment_modal(projected_catalog),
            _position_modal(),
        ],
        className='ada-operational-admin atlanticus-bootstrap',
    )


def _provider_label(label: str, name: str) -> object:
    return html.Div(
        [html.Span(label), html.Strong(name)],
        className='ada-operational-admin__provider',
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


def _surface_tab_class(active: bool) -> str:
    name = 'ada-operational-admin__primary-tab'
    return f'{name} {name}--active' if active else name


def _surface_class(active: bool) -> str:
    name = 'ada-operational-admin__surface'
    return f'{name} {name}--active' if active else name


def render_assignment_list(
    context: OperationalManagerContext,
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
        _, catalog = context.service.catalog_for_edit()
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
    context: OperationalManagerContext,
    query: str | None,
    number: int,
    size: int,
) -> tuple[object, Page[Position]]:
    _, catalog = context.service.catalog_for_edit()
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


def catalog_metadata(context: OperationalManagerContext, snapshot: SourceSnapshot) -> object:
    try:
        status = context.service.projection_status(CATALOG_SOURCE_KEY)
        state = _status_label(status)
        projected = _release_label(status.projected_source_release)
    except Exception:
        state, projected = 'Proyección no disponible', 'No verificable'
    source = _release_label(snapshot.current.release_ref if snapshot.current else None)
    return html.Div(
        [
            _metadata_cell('Source', source),
            _metadata_cell('Projection', projected),
            html.Span(state, className='ada-operational-admin__badge'),
        ],
        className='ada-operational-admin__metadata',
    )


def _assignment_row(
    context: OperationalManagerContext,
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
                    f'Cargo: {positions.get(assignment.position_id, assignment.position_id or "—")}',
                    f'Grupo: {assignment.group_id if assignment.group_id is not None else "—"}',
                )
            )
        )
    except Exception:
        state = 'Datos no disponibles'
        assignment_label = 'No verificable'
        details = 'No fue posible verificar Source y Projection.'
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
        **{'data-page-size': str(page.request.page_size)},
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
                dcc.Input(
                    id=ids.POSITION_LABEL,
                    type='text',
                    maxLength=120,
                    className='form-control',
                ),
            ),
            dcc.Checklist(
                id=ids.POSITION_ACTIVE,
                options=[{'label': 'Activo', 'value': 'active'}],
                value=['active'],
                className='ada-operational-admin__check',
            ),
            html.Div(id=ids.CATALOG_RESULT, role='status'),
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
                'Guardar cargo',
                id=ids.CATALOG_SAVE,
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
                '',
                id=backdrop_id,
                type='button',
                n_clicks=0,
                className='ada-operational-admin__modal-backdrop',
                **{'aria-label': 'Cerrar formulario'},
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(title),
                            html.Button(
                                '×',
                                id=close_id,
                                type='button',
                                n_clicks=0,
                                className='ada-operational-admin__close',
                                **{'aria-label': 'Cerrar formulario'},
                            ),
                        ],
                        className='ada-operational-admin__modal-head',
                    ),
                    html.Div(body, className='ada-operational-admin__modal-body'),
                    html.Div(actions, className='ada-operational-admin__modal-actions'),
                ],
                className='ada-operational-admin__modal-dialog',
                role='dialog',
                **{'aria-modal': 'true'},
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


def _tab_class(active: bool) -> str:
    base = 'ada-operational-admin__tab'
    return f'{base} {base}--active' if active else base


def _panel_class(active: bool) -> str:
    base = 'ada-operational-admin__panel'
    return f'{base} {base}--active' if active else base


def modal_class(opened: bool) -> str:
    base = 'ada-operational-admin__modal'
    return f'{base} {base}--open' if opened else base
