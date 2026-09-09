from __future__ import annotations

from dash.development.base_component import Component

from ada.web.configuration import (
    ConfigurationPageRequest,
    build_configuration_pagination,
    paginate_items,
)


def _prop(component: Component, name: str) -> object:
    return component.to_plotly_json()['props'].get(name)


def _walk(component: object) -> list[Component]:
    found: list[Component] = []
    if isinstance(component, Component):
        found.append(component)
        children = getattr(component, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found.extend(_walk(child))
        elif children is not None:
            found.extend(_walk(children))
    return found


def test_pagination_surface_exposes_ten_twenty_and_page_navigation() -> None:
    page = paginate_items(
        tuple(range(25)),
        ConfigurationPageRequest(page_number=2, page_size=10),
    )

    component = build_configuration_pagination(page, id_prefix='test')
    nodes = _walk(component)

    assert _prop(component, 'data-page') == '2'
    assert _prop(component, 'data-page-count') == '3'
    assert _prop(component, 'data-total-count') == '25'

    previous = next(node for node in nodes if getattr(node, 'id', None) == 'test--pagination-previous')
    following = next(node for node in nodes if getattr(node, 'id', None) == 'test--pagination-next')
    page_size = next(node for node in nodes if getattr(node, 'id', None) == 'test--pagination-page-size')

    assert previous.disabled is False
    assert following.disabled is False
    assert tuple(option['value'] for option in page_size.options) == (10, 20)
