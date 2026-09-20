import pytest

pytest.importorskip('dash')

from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.web.ids import group_add_link_id
from atlanticus.web.navigation.configuration.web.rendering import (
    navigation_structure_page,
    render_navigation_structure,
)
from atlanticus.web.pagination import PageRequest


def _link(index: int) -> NavigationLinkConfiguration:
    return NavigationLinkConfiguration(
        key=f'link-{index}',
        label=f'Link {index}',
        href=f'/link-{index}',
        order=index * 10,
    )


def _walk(component: object):
    yield component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float, bool)):
        yield from _walk(children)


def _has_id(component: object, component_id: object) -> bool:
    return any(getattr(item, 'id', None) == component_id for item in _walk(component))


def test_structure_paginates_only_top_level_nodes() -> None:
    group = NavigationGroupConfiguration(
        key='section',
        label='Section',
        order=15,
        links=tuple(_link(index + 100) for index in range(25)),
    )
    catalog = NavigationConfigurationCatalog(
        links=tuple(_link(index) for index in range(11)),
        groups=(group,),
    )

    first = navigation_structure_page(catalog, PageRequest(page_number=1, page_size=10))
    second = navigation_structure_page(catalog, PageRequest(page_number=2, page_size=10))

    assert first.total_count == 12
    assert len(first.items) == 10
    assert len(second.items) == 2


def test_structure_supports_twenty_top_level_rows() -> None:
    catalog = NavigationConfigurationCatalog(links=tuple(_link(index) for index in range(21)))

    page = navigation_structure_page(catalog, PageRequest(page_number=1, page_size=20))

    assert page.total_count == 21
    assert len(page.items) == 20
    assert page.page_count == 2


def test_section_children_are_collapsed_by_default_and_expand_together() -> None:
    group = NavigationGroupConfiguration(
        key='section',
        label='Section',
        links=(_link(1), _link(2)),
    )
    page = navigation_structure_page(
        NavigationConfigurationCatalog(groups=(group,)),
        PageRequest(),
    )

    collapsed = render_navigation_structure(page)
    expanded = render_navigation_structure(page, expanded_group_keys=('section',))

    assert not _has_id(collapsed, group_add_link_id('section'))
    assert _has_id(expanded, group_add_link_id('section'))


def test_pagination_clamps_after_top_level_items_are_removed() -> None:
    catalog = NavigationConfigurationCatalog(links=tuple(_link(index) for index in range(11)))

    page = navigation_structure_page(catalog, PageRequest(page_number=9, page_size=10))

    assert page.request.page_number == 2
    assert page.start_index == 11
    assert page.end_index == 11
