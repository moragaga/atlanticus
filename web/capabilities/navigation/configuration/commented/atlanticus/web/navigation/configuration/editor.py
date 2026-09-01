from __future__ import annotations

# El editor mantiene keys estables y permite mover enlaces entre raíz y secciones sin recrearlos.
# El orden superior combina enlaces raíz y secciones; cada sección mantiene su propio orden interno.


import re
import unicodedata
from dataclasses import replace

from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)

_NON_KEY_PATTERN = re.compile(r'[^a-z0-9._-]+')


def build_navigation_key(label: str) -> str:
    normalized = unicodedata.normalize('NFKD', label.strip())
    ascii_text = ''.join(
        character for character in normalized if not unicodedata.combining(character)
    )
    candidate = _NON_KEY_PATTERN.sub('-', ascii_text.casefold()).strip('-._')
    if not candidate:
        raise ValueError('Generated navigation key is invalid')
    return candidate


def build_initial_catalog() -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog()


def upsert_link(
    catalog: NavigationConfigurationCatalog,
    *,
    editor_key: str | None,
    parent_group_key: str | None,
    label: str,
    href: str,
    icon: str | None,
    enabled: bool,
    new_tab: bool,
    force_reload: bool,
    allowed_profiles: tuple[str, ...],
) -> NavigationConfigurationCatalog:
    key = editor_key or _unique_key(catalog, build_navigation_key(label))
    existing = _find_link(catalog, key)
    current_parent = link_parent_key(catalog, key) if existing is not None else None
    same_parent = existing is not None and current_parent == parent_group_key
    order = (
        existing.order
        if same_parent
        else _next_link_order(catalog, parent_group_key)
    )
    link = NavigationLinkConfiguration(
        key=key,
        label=label,
        href=href,
        order=order,
        icon=icon,
        enabled=enabled,
        new_tab=new_tab,
        force_reload=force_reload,
        allowed_profiles=allowed_profiles,
    )
    base = _detach_link(catalog, key) if existing is not None else catalog
    return _attach_link(base, link=link, parent_group_key=parent_group_key)


def create_group(
    catalog: NavigationConfigurationCatalog,
    *,
    label: str,
    icon: str | None,
    enabled: bool,
) -> NavigationConfigurationCatalog:
    group = NavigationGroupConfiguration(
        key=_unique_key(catalog, build_navigation_key(label)),
        label=label,
        order=_next_top_level_order(catalog),
        icon=icon,
        enabled=enabled,
    )
    return replace(catalog, groups=(*catalog.groups, group))


def update_group(
    catalog: NavigationConfigurationCatalog,
    *,
    key: str,
    label: str,
    icon: str | None,
    enabled: bool,
) -> NavigationConfigurationCatalog:
    found = False
    groups: list[NavigationGroupConfiguration] = []
    for group in catalog.groups:
        if group.key != key:
            groups.append(group)
            continue
        found = True
        groups.append(replace(group, label=label, icon=icon, enabled=enabled))
    if not found:
        raise ValueError('Navigation group does not exist')
    return replace(catalog, groups=tuple(groups))


def remove_group(
    catalog: NavigationConfigurationCatalog,
    *,
    key: str,
) -> NavigationConfigurationCatalog:
    nodes = _top_level_nodes(catalog)
    index = next((i for i, item in enumerate(nodes) if item[1].key == key), None)
    if index is None:
        raise ValueError('Navigation group does not exist')
    kind, group = nodes[index]
    if kind != 'group':
        raise ValueError('Navigation group does not exist')
    replacement = [('link', link) for link in sorted(group.links, key=_sort_key)]
    nodes[index:index + 1] = replacement
    return _catalog_from_top_level_nodes(catalog, nodes)


def remove_link(
    catalog: NavigationConfigurationCatalog,
    *,
    key: str,
) -> NavigationConfigurationCatalog:
    if _find_link(catalog, key) is None:
        raise ValueError('Navigation link does not exist')
    return _detach_link(catalog, key)


def reorder_root_node(
    catalog: NavigationConfigurationCatalog,
    *,
    key: str,
    direction: int,
) -> NavigationConfigurationCatalog:
    if direction not in {-1, 1}:
        raise ValueError('Navigation reorder direction is invalid')
    nodes = _top_level_nodes(catalog)
    index = next((i for i, item in enumerate(nodes) if item[1].key == key), None)
    if index is None:
        raise ValueError('Navigation root node does not exist')
    target = index + direction
    if target < 0 or target >= len(nodes):
        return catalog
    nodes[index], nodes[target] = nodes[target], nodes[index]
    return _catalog_from_top_level_nodes(catalog, nodes)


def reorder_link(
    catalog: NavigationConfigurationCatalog,
    *,
    key: str,
    direction: int,
) -> NavigationConfigurationCatalog:
    if direction not in {-1, 1}:
        raise ValueError('Navigation reorder direction is invalid')
    parent_key = link_parent_key(catalog, key)
    if parent_key is None:
        return reorder_root_node(catalog, key=key, direction=direction)
    groups: list[NavigationGroupConfiguration] = []
    found = False
    for group in catalog.groups:
        if group.key != parent_key:
            groups.append(group)
            continue
        links = list(sorted(group.links, key=_sort_key))
        index = next(i for i, link in enumerate(links) if link.key == key)
        target = index + direction
        if 0 <= target < len(links):
            links[index], links[target] = links[target], links[index]
        links = [replace(link, order=(i + 1) * 10) for i, link in enumerate(links)]
        groups.append(replace(group, links=tuple(links)))
        found = True
    if not found:
        raise ValueError('Navigation link does not exist')
    return replace(catalog, groups=tuple(groups))


def link_parent_key(catalog: NavigationConfigurationCatalog, key: str) -> str | None:
    for group in catalog.groups:
        if any(link.key == key for link in group.links):
            return group.key
    return None


def _detach_link(
    catalog: NavigationConfigurationCatalog,
    key: str,
) -> NavigationConfigurationCatalog:
    links = tuple(link for link in catalog.links if link.key != key)
    groups = tuple(
        replace(group, links=tuple(link for link in group.links if link.key != key))
        for group in catalog.groups
    )
    return replace(catalog, links=links, groups=groups)


def _attach_link(
    catalog: NavigationConfigurationCatalog,
    *,
    link: NavigationLinkConfiguration,
    parent_group_key: str | None,
) -> NavigationConfigurationCatalog:
    if parent_group_key is None:
        return replace(catalog, links=(*catalog.links, link))
    found = False
    groups: list[NavigationGroupConfiguration] = []
    for group in catalog.groups:
        if group.key == parent_group_key:
            groups.append(replace(group, links=(*group.links, link)))
            found = True
        else:
            groups.append(group)
    if not found:
        raise ValueError('Navigation group does not exist')
    return replace(catalog, groups=tuple(groups))


def _find_link(
    catalog: NavigationConfigurationCatalog,
    key: str,
) -> NavigationLinkConfiguration | None:
    for link in catalog.links:
        if link.key == key:
            return link
    for group in catalog.groups:
        for link in group.links:
            if link.key == key:
                return link
    return None


def _unique_key(catalog: NavigationConfigurationCatalog, candidate: str) -> str:
    existing = {link.key for link in catalog.links}
    existing.update(link.key for group in catalog.groups for link in group.links)
    existing.update(group.key for group in catalog.groups)
    if candidate not in existing:
        return candidate
    index = 2
    while f'{candidate}-{index}' in existing:
        index += 1
    return f'{candidate}-{index}'


def _next_top_level_order(catalog: NavigationConfigurationCatalog) -> int:
    values = [link.order for link in catalog.links]
    values.extend(group.order for group in catalog.groups)
    return max(values, default=0) + 10


def _next_link_order(catalog: NavigationConfigurationCatalog, group_key: str | None) -> int:
    if group_key is None:
        return _next_top_level_order(catalog)
    group = next((item for item in catalog.groups if item.key == group_key), None)
    if group is None:
        raise ValueError('Navigation group does not exist')
    return max((link.order for link in group.links), default=0) + 10


def _top_level_nodes(
    catalog: NavigationConfigurationCatalog,
) -> list[tuple[str, NavigationLinkConfiguration | NavigationGroupConfiguration]]:
    nodes: list[tuple[str, NavigationLinkConfiguration | NavigationGroupConfiguration]] = [
        ('link', link) for link in catalog.links
    ]
    nodes.extend(('group', group) for group in catalog.groups)
    return sorted(nodes, key=lambda item: _sort_key(item[1]))


def _catalog_from_top_level_nodes(
    catalog: NavigationConfigurationCatalog,
    nodes: list[tuple[str, NavigationLinkConfiguration | NavigationGroupConfiguration]],
) -> NavigationConfigurationCatalog:
    links: list[NavigationLinkConfiguration] = []
    groups: list[NavigationGroupConfiguration] = []
    for index, (kind, node) in enumerate(nodes):
        order = (index + 1) * 10
        if kind == 'link':
            links.append(replace(node, order=order))
        else:
            groups.append(replace(node, order=order))
    return replace(catalog, links=tuple(links), groups=tuple(groups))


def _sort_key(item: object) -> tuple[int, str, str]:
    return (item.order, item.label, item.key)
