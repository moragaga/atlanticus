from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from ada.web.shell.navigation.ids import AdaNavigationIds
from ada.web.shell.navigation.models import AdaNavigationAction, AdaNavigationView
from atlanticus.web.navigation.api import (
    NavigationGroup,
    NavigationLink,
    NavigationMenu,
    NavigationUser,
)


def build_ada_navigation_desktop_trigger() -> dbc.Button:
    return dbc.Button(
        id=AdaNavigationIds.DESKTOP_TOGGLE,
        className='ada-navigation__trigger ada-navigation__trigger--desktop d-none d-md-flex dark-theme',
        color='dark',
        n_clicks=0,
        title='Abrir navegación',
        children=[html.I(className='bi bi-chevron-left')],
    )


def build_ada_navigation_mobile_trigger() -> dbc.Button:
    return dbc.Button(
        id=AdaNavigationIds.MOBILE_TOGGLE,
        className='ada-navigation__trigger ada-navigation__trigger--mobile dark-theme',
        color='dark',
        n_clicks=0,
        title='Abrir navegación',
        children=[html.I(className='bi bi-list')],
    )


def build_ada_navigation_offcanvas(
    menu: NavigationMenu,
    *,
    view: AdaNavigationView | None = None,
) -> dbc.Offcanvas:
    resolved_view = view or AdaNavigationView()
    return dbc.Offcanvas(
        id=AdaNavigationIds.OFFCANVAS,
        title=_build_title(resolved_view),
        is_open=False,
        placement='end',
        className='ada-navigation__offcanvas',
        children=[
            dcc.Location(id=AdaNavigationIds.LOCATION, refresh=False),
            html.Div(
                _build_menu_content(menu, resolved_view),
                id=AdaNavigationIds.MENU_CONTENT,
                className='ada-navigation__content',
            ),
        ],
    )


def _build_title(view: AdaNavigationView) -> html.Div:
    brand_mark = (
        html.Img(
            src=view.brand_logo_src,
            alt=view.brand_logo_alt,
            className='ada-navigation__brand-logo',
        )
        if view.brand_logo_src is not None
        else html.Span('ADA', className='ada-navigation__brand-fallback')
    )
    return html.Div(
        className='ada-navigation__title',
        children=[
            brand_mark,
            html.Div(
                className='ada-navigation__title-copy',
                children=[
                    html.H5(view.title, className='ada-navigation__title-heading'),
                    (
                        html.P(view.subtitle, className='ada-navigation__title-subtitle')
                        if view.subtitle is not None
                        else None
                    ),
                ],
            ),
        ],
    )


def _build_menu_content(menu: NavigationMenu, view: AdaNavigationView) -> html.Div:
    nodes = sorted(
        [*menu.links, *menu.groups],
        key=lambda node: (node.order, node.label, node.key),
    )
    main_children = [_build_user_card(menu.user)]
    if view.action is not None:
        main_children.append(_build_action(view.action))
    main_children.extend(
        [
            html.Div(className='ada-navigation__divider'),
            _build_navigation_nodes(nodes),
        ]
    )
    return html.Div(
        className='ada-navigation__body',
        children=[
            html.Div(main_children, className='ada-navigation__main'),
            _build_footer(view),
        ],
    )


def _build_footer(view: AdaNavigationView) -> html.Div | None:
    if view.footer_logo_src is None and view.application_version is None:
        return None
    return html.Div(
        className='ada-navigation__footer',
        children=[
            (
                html.Img(
                    src=view.footer_logo_src,
                    alt=view.footer_logo_alt,
                    className='ada-navigation__footer-logo',
                )
                if view.footer_logo_src is not None
                else None
            ),
            (
                html.Div(
                    f'Versión {view.application_version}',
                    className='ada-navigation__version',
                )
                if view.application_version is not None
                else None
            ),
        ],
    )


def _build_user_card(user: NavigationUser) -> html.Div:
    return html.Div(
        className='ada-navigation__user',
        children=[
            _build_user_avatar(user),
            html.Div(
                className='ada-navigation__user-copy',
                children=[
                    html.H4(user.display_name, className='ada-navigation__user-name'),
                    (
                        html.P(user.email, className='ada-navigation__user-email')
                        if user.email is not None
                        else None
                    ),
                    html.Div(
                        className='ada-navigation__profile',
                        style={
                            'backgroundColor': user.profile_background_color,
                            'color': user.profile_text_color,
                        },
                        children=[
                            html.I(className='bi bi-person-badge me-1'),
                            html.Span(user.profile_label),
                        ],
                    ),
                ],
            ),
        ],
    )


def _build_user_avatar(user: NavigationUser) -> html.Img | html.Div:
    if user.avatar_src is not None:
        return html.Img(
            src=user.avatar_src,
            alt=user.display_name,
            className='ada-navigation__avatar',
        )
    return html.Div(
        user.avatar_text,
        className='ada-navigation__avatar ada-navigation__avatar--fallback',
        title=user.display_name,
        style={
            'backgroundColor': user.avatar_background_color,
            'color': user.avatar_text_color,
        },
    )


def _build_action(action: AdaNavigationAction) -> html.A:
    return html.A(
        href=action.href,
        target='_blank' if action.new_tab else '_self',
        rel='noopener noreferrer' if action.new_tab else None,
        className='ada-navigation__action text-decoration-none',
        children=[
            html.Span(
                className='ada-navigation__action-label',
                children=[
                    html.I(className=f'{action.icon} me-2') if action.icon else None,
                    html.Span(action.label),
                ],
            ),
            html.I(className='bi bi-box-arrow-up-right') if action.new_tab else None,
        ],
    )


def _build_navigation_nodes(nodes: list[NavigationLink | NavigationGroup]) -> html.Div:
    if not nodes:
        return html.Div(
            'No hay opciones de navegación disponibles.',
            className='ada-navigation__empty text-muted small',
        )
    return html.Div(
        [_build_node(node) for node in nodes],
        className='ada-navigation__menu d-flex flex-column',
    )


def _build_node(node: NavigationLink | NavigationGroup) -> html.Div | dcc.Link | html.A:
    if isinstance(node, NavigationGroup):
        return _build_group(node)
    return _build_link(node, is_child=False)


def _build_group(group: NavigationGroup) -> html.Div:
    group_class = 'ada-navigation__root-item ada-navigation__group'
    if not group.enabled:
        group_class += ' is-disabled'
    button_class = 'ada-navigation__button ada-navigation__group-button'
    if group.expanded:
        button_class += ' is-open'
    return html.Div(
        className=group_class,
        children=[
            html.Button(
                id=AdaNavigationIds.group_toggle(group.key),
                type='button',
                n_clicks=0,
                disabled=not group.enabled,
                className=button_class,
                children=[
                    html.Span(
                        className='ada-navigation__label d-flex align-items-center',
                        children=[
                            html.I(className=f'{group.icon} me-2') if group.icon else None,
                            html.Span(group.label),
                        ],
                    ),
                    html.I(className='bi bi-chevron-down ada-navigation__chevron'),
                ],
            ),
            dbc.Collapse(
                id=AdaNavigationIds.group_collapse(group.key),
                is_open=group.expanded,
                children=html.Div(
                    [
                        _build_link(link, is_child=True)
                        for link in sorted(
                            group.links,
                            key=lambda item: (item.order, item.label, item.key),
                        )
                    ],
                    className='ada-navigation__group-links d-flex flex-column',
                ),
            ),
        ],
    )


def _build_link(
    link: NavigationLink,
    *,
    is_child: bool,
) -> dcc.Link | html.A:
    button_class = 'ada-navigation__button ada-navigation__link'
    if is_child:
        button_class += ' ada-navigation__link--child'
    content = html.Button(
        type='button',
        tabIndex=-1,
        className=button_class,
        children=[
            html.I(className=f'{link.icon} me-2') if link.icon else None,
            html.Span(link.label),
        ],
    )
    wrapper_class = 'ada-navigation__link-wrapper d-block text-decoration-none'
    if not link.enabled:
        wrapper_class += ' is-disabled'
    common = {
        'id': AdaNavigationIds.link(link.key),
        'href': link.href,
        'className': wrapper_class,
        'children': content,
    }
    if link.new_tab or link.is_external:
        return html.A(
            target='_blank' if link.new_tab else '_self',
            rel='noopener noreferrer' if link.new_tab else None,
            **common,
        )
    return dcc.Link(
        target='_self',
        refresh=link.force_reload,
        **common,
    )
