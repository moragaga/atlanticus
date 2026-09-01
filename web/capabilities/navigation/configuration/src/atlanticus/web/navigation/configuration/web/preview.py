from __future__ import annotations

from dash import html

from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)


def build_navigation_history_preview(payload: dict[str, object]) -> object:
    catalog = NavigationConfigurationCatalog.from_document(payload)
    grouped_links = sum(len(group.links) for group in catalog.groups)
    profiles = catalog.configured_profiles()
    return html.Div(
        [
            _summary(
                (
                    ('Enlaces raíz', str(len(catalog.links))),
                    ('Secciones', str(len(catalog.groups))),
                    ('Enlaces en secciones', str(grouped_links)),
                    ('Perfiles referenciados', str(len(profiles))),
                )
            ),
            html.Div(
                [
                    _root_links(catalog.links),
                    *[_group(group) for group in sorted(catalog.groups, key=_sort_key)],
                ],
                className='atlanticus-manager__preview-tree',
            ),
        ],
        className='atlanticus-manager__preview-content',
    )


def _root_links(links: tuple[NavigationLinkConfiguration, ...]) -> object:
    return html.Section(
        [
            _section_heading('Raíz', 'Enlaces disponibles fuera de una sección.'),
            html.Div(
                [_link(link) for link in sorted(links, key=_sort_key)]
                if links
                else html.P('Sin enlaces raíz.', className='atlanticus-manager__preview-empty'),
                className='atlanticus-manager__preview-children',
            ),
        ],
        className='atlanticus-manager__preview-section',
    )


def _group(group: NavigationGroupConfiguration) -> object:
    return html.Section(
        [
            _section_heading(
                group.label,
                group.key,
                badges=(
                    _badge(f'Orden {group.order}'),
                    _badge('Habilitada' if group.enabled else 'Deshabilitada'),
                    *(_optional_badge(f'Icono {group.icon}') if group.icon else ()),
                ),
            ),
            html.Div(
                [_link(link) for link in sorted(group.links, key=_sort_key)]
                if group.links
                else html.P(
                    'Sin enlaces en esta sección.',
                    className='atlanticus-manager__preview-empty',
                ),
                className='atlanticus-manager__preview-children',
            ),
        ],
        className='atlanticus-manager__preview-section',
    )


def _link(link: NavigationLinkConfiguration) -> object:
    profiles = ', '.join(link.allowed_profiles) if link.allowed_profiles else 'Acceso total'
    badges = [
        _badge(f'Orden {link.order}'),
        _badge('Habilitado' if link.enabled else 'Deshabilitado'),
        _badge(f'Perfiles: {profiles}'),
    ]
    if link.new_tab:
        badges.append(_badge('Nueva pestaña'))
    if link.force_reload:
        badges.append(_badge('Recarga completa'))
    if link.icon:
        badges.append(_badge(f'Icono {link.icon}'))
    return html.Article(
        [
            html.Div(
                [html.Strong(link.label), html.Code(link.key)],
                className='atlanticus-manager__preview-entity-title',
            ),
            html.Div(link.href, className='atlanticus-manager__preview-url'),
            html.Div(badges, className='atlanticus-manager__preview-badges'),
        ],
        className='atlanticus-manager__preview-entity',
    )


def _section_heading(
    title: str,
    detail: str,
    *,
    badges: tuple[object, ...] = (),
) -> object:
    return html.Header(
        [
            html.Div(
                [html.Strong(title), html.Small(detail)],
                className='atlanticus-manager__preview-section-copy',
            ),
            html.Div(list(badges), className='atlanticus-manager__preview-badges')
            if badges
            else None,
        ],
        className='atlanticus-manager__preview-section-heading',
    )


def _summary(items: tuple[tuple[str, str], ...]) -> object:
    return html.Div(
        [
            html.Div(
                [html.Small(label), html.Strong(value)],
                className='atlanticus-manager__preview-summary-item',
            )
            for label, value in items
        ],
        className='atlanticus-manager__preview-summary',
    )


def _badge(label: str) -> object:
    return html.Span(label, className='atlanticus-manager__preview-badge')


def _optional_badge(label: str) -> tuple[object, ...]:
    return (_badge(label),)


def _sort_key(item: object) -> tuple[int, str, str]:
    return (item.order, item.label, item.key)
