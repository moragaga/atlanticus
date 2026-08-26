from __future__ import annotations

from importlib.resources import files

import pytest
from dash.development.base_component import Component

from ada.web.ui.branding import (
    ADA_BRANDING_ASSET_LAYER,
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    OperationalBrandState,
    build_operational_brand,
    create_ada_branding_module,
)


def test_branding_module_publishes_small_operational_asset_layer() -> None:
    module = create_ada_branding_module()
    resource = files('ada.web.ui.branding').joinpath('resources/img/ada-operational-primary.png')

    assert module.name == 'ada-branding'
    assert module.asset_layers == (ADA_BRANDING_ASSET_LAYER,)
    assert DEFAULT_OPERATIONAL_BRAND_LOGO_SRC == (
        f'/assets/{ADA_BRANDING_ASSET_LAYER.target_name}/img/ada-operational-primary.png'
    )
    assert resource.is_file()
    assert len(resource.read_bytes()) < 100_000


def test_operational_brand_renders_injected_context_without_header_dependency() -> None:
    component = build_operational_brand(
        OperationalBrandState(context_name='Operaciones Integradas')
    )

    assert _prop(component, 'data-ada-component-key') == 'operational_brand'
    logo = _require_by_class(component, 'ada-operational-brand__logo')
    context = _require_by_class(component, 'ada-operational-brand__context')

    assert _prop(logo, 'src') == DEFAULT_OPERATIONAL_BRAND_LOGO_SRC
    assert _prop(logo, 'alt') == 'ADA'
    assert 'Operaciones Integradas' in _text_content(context)
    assert _find_by_class(component, 'ada-header') is None


def test_operational_brand_does_not_invent_context_when_configuration_is_absent() -> None:
    component = build_operational_brand(OperationalBrandState())

    assert _find_by_class(component, 'ada-operational-brand__context') is None
    assistant = _require_by_class(component, 'ada-operational-brand__assistant')
    assert _text_content(assistant) == 'Asistente de Decisiones Ágiles'


def test_operational_brand_rejects_blank_text_contracts() -> None:
    with pytest.raises(ValueError, match='context_name cannot be empty'):
        OperationalBrandState(context_name='   ')
    with pytest.raises(ValueError, match='assistant_label cannot be empty'):
        OperationalBrandState(assistant_label='')
    with pytest.raises(ValueError, match='logo_src cannot be empty'):
        OperationalBrandState(logo_src='  ')


def _require_by_class(component: Component, class_name: str) -> Component:
    result = _find_by_class(component, class_name)
    if result is None:
        raise AssertionError(f'Component with class {class_name!r} was not found')
    return result


def _find_by_class(component: Component, class_name: str) -> Component | None:
    classes = getattr(component, 'className', '') or ''
    if class_name in classes.split():
        return component
    for child in _children(component):
        result = _find_by_class(child, class_name)
        if result is not None:
            return result
    return None


def _children(component: Component) -> list[Component]:
    children = getattr(component, 'children', None)
    if children is None:
        return []
    if not isinstance(children, (list, tuple)):
        children = [children]
    return [child for child in children if isinstance(child, Component)]


def _prop(component: Component, name: str):
    return component.to_plotly_json()['props'][name]


def _text_content(component: Component) -> str:
    children = getattr(component, 'children', None)
    if isinstance(children, str):
        return children
    if children is None:
        return ''
    if not isinstance(children, (list, tuple)):
        children = [children]
    return ''.join(
        child if isinstance(child, str) else _text_content(child)
        for child in children
        if isinstance(child, (str, Component))
    )
