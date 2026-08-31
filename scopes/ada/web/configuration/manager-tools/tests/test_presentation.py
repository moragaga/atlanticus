from dash.development.base_component import Component

from ada.configuration.branding import BrandingVariant
from ada.web.configuration.manager_tools import build_manager_tools_page
from ada.web.configuration.manager_tools.ids import BRANDING_VARIANT_ID, ROOT_ID
from ada.web.configuration.tool_editor import CONFIGURATION_STORE_ID


def _components(root: Component):
    yield root
    children = getattr(root, 'children', None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        iterable = children
    else:
        iterable = (children,)
    for child in iterable:
        if isinstance(child, Component):
            yield from _components(child)


def test_page_composes_branding_and_existing_source_editor() -> None:
    page = build_manager_tools_page()
    components = tuple(_components(page))
    ids = {getattr(component, 'id', None) for component in components}

    assert page.id == ROOT_ID
    assert BRANDING_VARIANT_ID in ids
    assert CONFIGURATION_STORE_ID in ids


def test_branding_dropdown_has_no_automatic_option() -> None:
    page = build_manager_tools_page()
    dropdown = next(
        component
        for component in _components(page)
        if getattr(component, 'id', None) == BRANDING_VARIANT_ID
    )

    values = {option['value'] for option in dropdown.options}
    assert values == {variant.value for variant in BrandingVariant}
    assert 'auto' not in values
