# Esta presentación pagina únicamente los nodos de primer nivel.
# Los enlaces internos pertenecen a su sección y sólo aparecen cuando la sección se expande.
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.web.ids import (
    STRUCTURE_NEXT_ID,
    STRUCTURE_PAGE_SIZE_ID,
    STRUCTURE_PREVIOUS_ID,
    group_add_link_id,
    group_delete_id,
    group_down_id,
    group_edit_id,
    group_toggle_id,
    group_up_id,
    link_delete_id,
    link_down_id,
    link_edit_id,
    link_up_id,
    structure_page_id,
)
from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, Page, PageRequest, paginate_items

NavigationStructureNode = tuple[
    str,
    NavigationLinkConfiguration | NavigationGroupConfiguration,
]


def navigation_structure_page(
    catalog: NavigationConfigurationCatalog,
    request: PageRequest,
) -> Page[NavigationStructureNode]:
    nodes: list[NavigationStructureNode] = [('link', link) for link in catalog.links]
    nodes.extend(('group', group) for group in catalog.groups)
    nodes.sort(key=lambda item: _sort_key(item[1]))
    return paginate_items(tuple(nodes), request)


def render_navigation_structure(
    page: Page[NavigationStructureNode],
    *,
    expanded_group_keys: tuple[str, ...] = (),
) -> object:
    expanded = frozenset(expanded_group_keys)
    if page.items:
        content = [
            _link_card(node, parent_key=None)
            if kind == 'link'
            else _group_card(node, expanded=node.key in expanded)
            for kind, node in page.items
        ]
    else:
        content = [
            html.Div(
                [
                    html.Span(
                        '+',
                        className='atlanticus-navigation-admin__empty-icon',
                        **{'aria-hidden': 'true'},
                    ),
                    html.Strong('Todavía no hay navegación configurada.'),
                    html.Span('Agrega el primer enlace o sección para comenzar.'),
                ],
                className='atlanticus-navigation-admin__empty-state',
                role='status',
            )
        ]
    results_class = 'atlanticus-navigation-admin__structure-results'
    if not page.items:
        results_class += ' atlanticus-navigation-admin__structure-results--empty'
    return html.Div(
        [
            html.Div(content, className=results_class),
            _pagination(page),
        ],
        className='atlanticus-navigation-admin__structure',
        **{
            'data-page-size': str(page.request.page_size),
            'data-total-count': str(page.total_count),
        },
    )


def navigation_section_options(
    catalog: NavigationConfigurationCatalog,
) -> list[dict[str, str]]:
    groups = sorted(catalog.groups, key=_sort_key)
    return [
        {'label': 'Sin sección / raíz', 'value': '__root__'},
        *[{'label': group.label, 'value': group.key} for group in groups],
    ]


def _group_card(group: NavigationGroupConfiguration, *, expanded: bool) -> object:
    flags = ['DESHABILITADA'] if not group.enabled else []
    child_count = len(group.links)
    detail = f'{child_count} enlace' if child_count == 1 else f'{child_count} enlaces'
    children = None
    add_link = None
    if expanded:
        child_nodes = [
            _link_card(link, parent_key=group.key)
            for link in sorted(group.links, key=_sort_key)
        ]
        if not child_nodes:
            child_nodes = [
                html.P(
                    'No hay enlaces en esta sección.',
                    className='atlanticus-navigation-admin__empty-child',
                )
            ]
        children = html.Div(child_nodes, className='atlanticus-navigation-admin__children')
        add_link = dbc.Button(
            '+ Enlace',
            id=group_add_link_id(group.key),
            n_clicks=0,
            color='secondary',
            outline=True,
            size='sm',
        )
    return html.Article(
        [
            html.Div(
                [
                    _card_copy(group.label, group.key, None, flags, detail=detail),
                    _group_actions(group.key, expanded=expanded),
                ],
                className='atlanticus-navigation-admin__card-head',
            ),
            children,
            add_link,
        ],
        className=(
            'atlanticus-navigation-admin__group-card '
            'atlanticus-navigation-admin__group-card--expanded'
            if expanded
            else 'atlanticus-navigation-admin__group-card'
        ),
    )


def _link_card(link: NavigationLinkConfiguration, *, parent_key: str | None) -> object:
    flags = []
    if not link.enabled:
        flags.append('DESHABILITADO')
    if link.new_tab:
        flags.append('NUEVA PESTAÑA')
    if link.force_reload:
        flags.append('RECARGA')
    return html.Article(
        [
            _card_copy(
                link.label,
                link.key,
                link.href,
                flags,
                profiles=link.allowed_profiles,
            ),
            html.Div(
                [
                    _mini_button('↑', link_up_id(link.key)),
                    _mini_button('↓', link_down_id(link.key)),
                    _mini_button('Editar', link_edit_id(link.key)),
                    _mini_button('Eliminar', link_delete_id(link.key)),
                ],
                className='atlanticus-navigation-admin__actions',
            ),
        ],
        className=(
            'atlanticus-navigation-admin__link-card '
            + ('atlanticus-navigation-admin__link-card--child' if parent_key else '')
        ).strip(),
    )


def _card_copy(
    label: str,
    key: str,
    href: str | None,
    flags: list[str],
    *,
    profiles: tuple[str, ...] | None = None,
    detail: str | None = None,
) -> object:
    metadata = []
    if href is not None:
        metadata.append(html.Span(href))
    if detail is not None:
        metadata.append(html.Small(detail))
    if profiles is not None:
        metadata.append(
            html.Small(
                f'Perfiles: {_profiles_text(profiles)}' if profiles else 'Acceso: Público'
            )
        )
    if flags:
        metadata.append(html.Small(' · '.join(flags)))
    return html.Div(
        [
            html.Div(
                [html.Strong(label), html.Code(key)],
                className='atlanticus-navigation-admin__card-title',
            ),
            html.Div(metadata, className='atlanticus-navigation-admin__card-meta'),
        ],
        className='atlanticus-navigation-admin__card-copy',
    )


def _group_actions(key: str, *, expanded: bool) -> object:
    return html.Div(
        [
            _mini_button('↑', group_up_id(key)),
            _mini_button('↓', group_down_id(key)),
            _mini_button('Editar', group_edit_id(key)),
            _mini_button('Eliminar', group_delete_id(key)),
            _mini_button('Contraer' if expanded else 'Expandir', group_toggle_id(key)),
        ],
        className='atlanticus-navigation-admin__actions',
    )


def _pagination(page: Page[NavigationStructureNode]) -> object:
    return html.Div(
        [
            html.Div(
                _summary(page),
                className='atlanticus-navigation-admin__pagination-summary',
                **{'aria-live': 'polite'},
            ),
            html.Div(
                [
                    html.Button(
                        '‹',
                        id=STRUCTURE_PREVIOUS_ID,
                        type='button',
                        disabled=not page.has_previous,
                        className='atlanticus-navigation-admin__pagination-button',
                        **{'aria-label': 'Página anterior'},
                    ),
                    *_page_buttons(page),
                    html.Button(
                        '›',
                        id=STRUCTURE_NEXT_ID,
                        type='button',
                        disabled=not page.has_next,
                        className='atlanticus-navigation-admin__pagination-button',
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='atlanticus-navigation-admin__pagination-navigation',
            ),
            html.Label(
                [
                    html.Span(
                        'Filas',
                        className='atlanticus-navigation-admin__pagination-page-size-label',
                    ),
                    html.Div(
                        dcc.Dropdown(
                            id=STRUCTURE_PAGE_SIZE_ID,
                            options=[
                                {'label': str(value), 'value': value}
                                for value in ALLOWED_PAGE_SIZES
                            ],
                            value=page.request.page_size,
                            clearable=False,
                            searchable=False,
                            style=_pagination_select_style(),
                        ),
                        className=(
                            'atlanticus-navigation-admin__dash-select-shell '
                            'atlanticus-navigation-admin__pagination-page-size'
                        ),
                    ),
                ],
                className='atlanticus-navigation-admin__pagination-page-size-control',
            ),
        ],
        className='atlanticus-navigation-admin__pagination',
        **{
            'data-page': str(page.request.page_number),
            'data-page-count': str(page.page_count),
            'data-total-count': str(page.total_count),
        },
    )


def _page_buttons(page: Page[NavigationStructureNode]) -> list[object]:
    nodes: list[object] = []
    for value in _visible_page_tokens(
        current=page.request.page_number,
        total=page.page_count,
    ):
        if value is None:
            nodes.append(
                html.Span(
                    '…',
                    className='atlanticus-navigation-admin__pagination-ellipsis',
                    **{'aria-hidden': 'true'},
                )
            )
            continue
        current = value == page.request.page_number
        nodes.append(
            html.Button(
                str(value),
                id=structure_page_id(value),
                type='button',
                disabled=current,
                className=(
                    'atlanticus-navigation-admin__pagination-button '
                    'atlanticus-navigation-admin__pagination-button--active'
                    if current
                    else 'atlanticus-navigation-admin__pagination-button'
                ),
                **{
                    'aria-label': f'Página {value}',
                    'aria-current': 'page' if current else 'false',
                },
            )
        )
    return nodes


def _summary(page: Page[NavigationStructureNode]) -> str:
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


def _mini_button(label: str, component_id: object) -> object:
    return dbc.Button(
        label,
        id=component_id,
        n_clicks=0,
        color='secondary',
        outline=True,
        size='sm',
    )


def _profiles_text(profiles: tuple[str, ...]) -> str:
    return ', '.join(profiles)


def _sort_key(item: object) -> tuple[int, str, str]:
    return (item.order, item.label, item.key)


def _pagination_select_style() -> dict[str, str]:
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
