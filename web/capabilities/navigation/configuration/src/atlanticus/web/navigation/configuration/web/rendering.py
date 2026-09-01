from __future__ import annotations

from dash import html

from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.web.ids import (
    group_add_link_id,
    group_delete_id,
    group_down_id,
    group_edit_id,
    group_up_id,
    link_delete_id,
    link_down_id,
    link_edit_id,
    link_up_id,
)


def navigation_structure(catalog: NavigationConfigurationCatalog) -> object:
    nodes = [('link', link) for link in catalog.links]
    nodes.extend(('group', group) for group in catalog.groups)
    nodes.sort(key=lambda item: _sort_key(item[1]))
    if not nodes:
        return html.P(
            'No hay enlaces ni secciones configuradas.',
            className='atlanticus-navigation-admin__empty',
        )
    return [
        _link_card(node, parent_key=None) if kind == 'link' else _group_card(node)
        for kind, node in nodes
    ]


def navigation_section_options(
    catalog: NavigationConfigurationCatalog,
) -> list[dict[str, str]]:
    groups = sorted(catalog.groups, key=_sort_key)
    return [
        {'label': 'Sin sección / raíz', 'value': '__root__'},
        *[{'label': group.label, 'value': group.key} for group in groups],
    ]


def _group_card(group) -> object:
    children = [
        _link_card(link, parent_key=group.key) for link in sorted(group.links, key=_sort_key)
    ]
    if not children:
        children = [
            html.P(
                'No hay enlaces en esta sección.',
                className='atlanticus-navigation-admin__empty-child',
            )
        ]
    flags = ['DESHABILITADA'] if not group.enabled else []
    return html.Article(
        [
            html.Div(
                [
                    _card_copy(group.label, group.key, None, flags),
                    _group_actions(group.key),
                ],
                className='atlanticus-navigation-admin__card-head',
            ),
            html.Div(children, className='atlanticus-navigation-admin__children'),
            html.Button(
                '+ Enlace',
                id=group_add_link_id(group.key),
                n_clicks=0,
                className=(
                    'atlanticus-manager__button '
                    'atlanticus-manager__button--secondary '
                    'atlanticus-navigation-admin__group-add'
                ),
            ),
        ],
        className='atlanticus-navigation-admin__group-card',
    )


def _link_card(link, *, parent_key: str | None) -> object:
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
) -> object:
    metadata = []
    if href is not None:
        metadata.append(html.Span(href))
    if profiles is not None:
        metadata.append(html.Small(f'Perfiles: {_profiles_text(profiles)}'))
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


def _group_actions(key: str) -> object:
    return html.Div(
        [
            _mini_button('↑', group_up_id(key)),
            _mini_button('↓', group_down_id(key)),
            _mini_button('Editar', group_edit_id(key)),
            _mini_button('Eliminar', group_delete_id(key)),
        ],
        className='atlanticus-navigation-admin__actions',
    )


def _mini_button(label: str, component_id: object) -> object:
    return html.Button(
        label,
        id=component_id,
        n_clicks=0,
        className='atlanticus-navigation-admin__mini-button',
    )


def _profiles_text(profiles: tuple[str, ...]) -> str:
    return ', '.join(profiles) if profiles else 'solo acceso total'


def _sort_key(item: object) -> tuple[int, str, str]:
    return (item.order, item.label, item.key)
