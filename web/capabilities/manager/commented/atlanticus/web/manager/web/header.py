# Espejo pedagógico: el Manager compone identidad y controles, sin logos fijos de ADA.
from __future__ import annotations

from dash import dcc, html

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.models import ManagerHeaderBrandMark, ManagerPrincipal
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.ids import HEADER_SECTION_ID


def build_manager_header(
    *,
    registry: ManagerModuleRegistry,
    principal: ManagerPrincipal,
    application_home_href: str | None,
    brand_marks: tuple[ManagerHeaderBrandMark, ...] = (),
    title: str = 'Manager',
    subtitle: str | None = None,
) -> object:
    # Los logos provienen de la aplicación consumidora; cualquier marca puede omitirse.
    product = next((mark for mark in brand_marks if mark.role == 'product'), None)
    supporting = tuple(
        mark
        for role in ('framework', 'organization')
        if (mark := next((entry for entry in brand_marks if entry.role == role), None))
        is not None
    )
    # Los enlaces administrativos mantienen el contrato anterior.
    actions = [
        dcc.Link(
            'Manager Home',
            href=registry.root_route,
            className='atlanticus-manager__header-link',
        )
    ]
    if application_home_href is not None:
        actions.append(
            dcc.Link(
                'Volver a la aplicación',
                href=application_home_href,
                className='atlanticus-manager__header-link atlanticus-manager__header-link--return',
            )
        )
    return html.Header(
        [
            html.Div(
                [
                    _brand_mark(product) if product is not None else None,
                    html.Div(
                        [
                            html.Strong(title, className='atlanticus-manager__header-name'),
                            html.Span(
                                'Inicio', id=HEADER_SECTION_ID,
                                className='atlanticus-manager__header-section',
                            ),
                            html.Span(subtitle, className='atlanticus-manager__header-subtitle')
                            if subtitle is not None else None,
                        ],
                        className='atlanticus-manager__header-context',
                    ),
                    html.Div(
                        [_brand_mark(mark) for mark in supporting],
                        className='atlanticus-manager__header-supporting',
                    ) if supporting else None,
                ],
                className='atlanticus-manager__header-identity',
            ),
            html.Div(
                [
                    html.Nav(
                        actions,
                        className='atlanticus-manager__header-actions',
                        **{'aria-label': 'Accesos del Manager'},
                    ),
                ],
                className='atlanticus-manager__header-end',
            ),
        ],
        className='atlanticus-manager__header',
    )


def _brand_mark(mark: ManagerHeaderBrandMark) -> object:
    return html.Div(
        [
            html.Img(src=mark.logo_src, alt=mark.logo_alt),
            html.Div(
                [
                    html.Small(mark.eyebrow) if mark.eyebrow is not None else None,
                    html.Span(mark.label) if mark.label is not None else None,
                ],
                className='atlanticus-manager__brand-caption',
            ) if mark.eyebrow is not None or mark.label is not None else None,
        ],
        className=f'atlanticus-manager__brand-mark atlanticus-manager__brand-mark--{mark.role}',
    )


def resolve_manager_header_section(
    *,
    pathname: str | None,
    registry: ManagerModuleRegistry,
    principal: ManagerPrincipal,
    authorization: ManagerAuthorizationPolicy,
) -> str:
    route = pathname or registry.root_route
    if route == registry.root_route:
        return 'Inicio'
    item = registry.find_by_route(route)
    if item is None or not authorization.can_view(principal, item):
        return 'Administración'
    return item.title
