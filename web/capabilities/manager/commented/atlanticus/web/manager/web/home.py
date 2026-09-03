# Home genérica del Manager: presenta módulos visibles y su estado sin incorporar dominio ADA.
# La paginación es exclusivamente de presentación y mantiene seis módulos por página.
# Las acciones de lifecycle permanecen dentro de cada módulo; las cards sólo informan y navegan.

from __future__ import annotations

from collections.abc import Mapping
from math import ceil

from dash import dcc, html

from atlanticus.web.manager.models import ManagerModule
from atlanticus.web.manager.projection import ProjectionState
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.ids import (
    HOME_CARDS_ID,
    HOME_NEXT_ID,
    HOME_PAGE_LABEL_ID,
    HOME_PAGE_STORE_ID,
    HOME_PREVIOUS_ID,
)

HOME_PAGE_SIZE = 6

_STATE_LABELS = {
    ProjectionState.NO_SOURCE: 'Sin fuente',
    ProjectionState.SYNCHRONIZED: 'Actualizada',
    ProjectionState.READY: 'Lista',
    ProjectionState.UNAVAILABLE: 'No disponible',
}


def paginate_home_modules(
    modules: tuple[ManagerModule, ...],
    page: int | None,
) -> tuple[tuple[ManagerModule, ...], int, int]:
    page_count = max(1, ceil(len(modules) / HOME_PAGE_SIZE))
    requested_page = page if isinstance(page, int) and not isinstance(page, bool) else 1
    current_page = min(max(requested_page, 1), page_count)
    start = (current_page - 1) * HOME_PAGE_SIZE
    return modules[start : start + HOME_PAGE_SIZE], current_page, page_count


def build_manager_home(
    *,
    registry: ManagerModuleRegistry,
    modules: tuple[ManagerModule, ...],
    states: Mapping[str, ProjectionState],
) -> object:
    cards, page_label, previous_disabled, next_disabled, current_page = (
        build_home_page_content(
            registry=registry,
            modules=modules,
            states=states,
            page=1,
        )
    )
    return html.Section(
        [
            html.Header(
                [
                    html.P('Administración', className='atlanticus-manager__eyebrow'),
                    html.H1('Manager'),
                    html.P(
                        'Administra configuraciones y revisa su estado desde un único punto.'
                    ),
                ],
                className='atlanticus-manager__home-header',
            ),
            dcc.Store(
                id=HOME_PAGE_STORE_ID,
                data=current_page,
                storage_type='memory',
            ),
            html.Div(
                cards,
                id=HOME_CARDS_ID,
                className='atlanticus-manager__home-grid',
            ),
            html.Nav(
                [
                    html.Button(
                        '‹',
                        id=HOME_PREVIOUS_ID,
                        n_clicks=0,
                        disabled=previous_disabled,
                        className=(
                            'atlanticus-manager__button '
                            'atlanticus-manager__button--secondary '
                            'atlanticus-manager__home-pagination-button'
                        ),
                        **{'aria-label': 'Página anterior'},
                    ),
                    html.Span(
                        page_label,
                        id=HOME_PAGE_LABEL_ID,
                        className='atlanticus-manager__home-page-label',
                    ),
                    html.Button(
                        '›',
                        id=HOME_NEXT_ID,
                        n_clicks=0,
                        disabled=next_disabled,
                        className=(
                            'atlanticus-manager__button '
                            'atlanticus-manager__button--secondary '
                            'atlanticus-manager__home-pagination-button'
                        ),
                        **{'aria-label': 'Página siguiente'},
                    ),
                ],
                className='atlanticus-manager__home-pagination',
                **{'aria-label': 'Paginación de configuraciones'},
            ),
        ],
        className='atlanticus-manager__home',
    )


def build_home_page_content(
    *,
    registry: ManagerModuleRegistry,
    modules: tuple[ManagerModule, ...],
    states: Mapping[str, ProjectionState],
    page: int | None,
) -> tuple[tuple[object, ...], str, bool, bool, int]:
    page_modules, current_page, page_count = paginate_home_modules(modules, page)
    return (
        build_home_cards(
            registry=registry,
            modules=page_modules,
            states=states,
        ),
        f'{current_page} / {page_count}',
        current_page <= 1,
        current_page >= page_count,
        current_page,
    )


def build_home_cards(
    *,
    registry: ManagerModuleRegistry,
    modules: tuple[ManagerModule, ...],
    states: Mapping[str, ProjectionState],
) -> tuple[object, ...]:
    if not modules:
        return (
            html.Div(
                'No hay configuraciones disponibles para este usuario.',
                className='atlanticus-manager__home-empty',
            ),
        )

    return tuple(
        _build_home_card(
            registry=registry,
            module=module,
            state=states.get(module.key, ProjectionState.UNAVAILABLE),
        )
        for module in modules
    )


def build_manager_home_return(home_route: str) -> object:
    return dcc.Link(
        '‹ Manager Home',
        href=home_route,
        className='atlanticus-manager__home-return',
    )


def _build_home_card(
    *,
    registry: ManagerModuleRegistry,
    module: ManagerModule,
    state: ProjectionState,
) -> object:
    return dcc.Link(
        [
            html.Div(
                [
                    html.Strong(module.title),
                    html.Span(
                        _STATE_LABELS[state],
                        className=(
                            'atlanticus-manager__state '
                            f'atlanticus-manager__state--{state.value}'
                        ),
                    ),
                ],
                className='atlanticus-manager__home-card-header',
            ),
            html.P(module.description or 'Configuración administrativa.'),
            html.Span('Abrir →', className='atlanticus-manager__home-card-action'),
        ],
        href=registry.route_for(module),
        className='atlanticus-manager__home-card',
    )
