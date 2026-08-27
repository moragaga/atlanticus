from importlib.resources import files
from pathlib import Path

from dash import html
from dash.development.base_component import Component

from ada.web.shell.header import (
    ADA_OPERATIONAL_HEADER_ASSET_LAYER,
    build_ada_operational_header,
    create_ada_operational_header_module,
)


def test_header_module_declares_only_header_assets() -> None:
    module = create_ada_operational_header_module()

    assert module.name == 'ada-operational-header'
    assert module.asset_layers == (ADA_OPERATIONAL_HEADER_ASSET_LAYER,)
    assert ADA_OPERATIONAL_HEADER_ASSET_LAYER.load_order == 220
    assert ADA_OPERATIONAL_HEADER_ASSET_LAYER.package == 'ada.web.shell.header'


def test_header_css_is_packaged() -> None:
    css_root = files('ada.web.shell.header').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()

    assert entries == ['10-operational-header.css']
    assert css_root.joinpath(entries[0]).is_file()


def test_header_owns_slots_without_knowing_their_presentations() -> None:
    brand = html.Div('brand', id='brand-component')
    indicators = html.Div('indicators', id='indicators-component')
    management = html.Div('management', id='management-component')
    status = html.Div('status', id='status-component')
    desktop = html.Button('desktop', id='desktop-navigation')
    mobile = html.Button('mobile', id='mobile-navigation')

    component = build_ada_operational_header(
        brand=brand,
        global_indicators=indicators,
        alarm_management=management,
        alarm_status=status,
        desktop_navigation_trigger=desktop,
        mobile_navigation_trigger=mobile,
    )

    assert _prop(component, 'data-ada-component-key') == 'operational_header'
    assert _require_slot(component, 'brand') is not None
    assert _require_slot(component, 'global_indicators') is not None
    assert _require_slot(component, 'alarm_management') is not None
    assert _require_slot(component, 'alarm_status') is not None
    assert _require_slot(component, 'navigation_desktop') is not None
    assert _require_slot(component, 'navigation_mobile') is not None
    assert _require_id(component, 'brand-component') is brand
    assert _require_id(component, 'indicators-component') is indicators
    assert _require_id(component, 'management-component') is management
    assert _require_id(component, 'status-component') is status
    assert _require_id(component, 'desktop-navigation') is desktop
    assert _require_id(component, 'mobile-navigation') is mobile


def test_optional_operational_slots_are_empty_without_placeholders() -> None:
    component = build_ada_operational_header(brand=html.Div('brand'))

    for slot_key in ('global_indicators', 'alarm_management', 'alarm_status'):
        slot = _require_slot(component, slot_key)
        assert _prop(slot, 'data-slot-empty') == 'true'
        assert _children(slot) == []


def test_brand_slot_remains_present_when_other_capabilities_are_missing() -> None:
    component = build_ada_operational_header(brand=html.Div('ADA', id='brand'))

    brand_slot = _require_slot(component, 'brand')
    assert _prop(brand_slot, 'data-slot-empty') == 'false'
    assert _require_id(brand_slot, 'brand') is not None


def test_header_css_prioritizes_global_indicators_over_alarm_slots() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    assert '--ada-operational-header-global-grow: 2.4;' in css
    assert '--ada-operational-header-management-grow: 1.45;' in css
    assert '--ada-operational-header-status-grow: 1.25;' in css


def test_header_source_has_no_tool_or_alarm_domain_imports() -> None:
    source = (
        Path(__file__)
        .parents[1]
        .joinpath('src/ada/web/shell/header/presentation.py')
        .read_text(encoding='utf-8')
    )

    assert 'ToolManifest' not in source
    assert 'GlobalIndicator' not in source
    assert 'Alarm' not in source
    assert 'ServiceRegistry' not in source


def _require_slot(component: Component, slot_key: str) -> Component:
    result = _find(component, property_name='data-ada-slot-key', value=slot_key)
    if result is None:
        raise AssertionError(f'Slot {slot_key!r} was not found')
    return result


def _require_id(component: Component, component_id: str) -> Component:
    result = _find(component, property_name='id', value=component_id)
    if result is None:
        raise AssertionError(f'Component id {component_id!r} was not found')
    return result


def _find(
    component: Component,
    *,
    property_name: str,
    value: str,
) -> Component | None:
    if _prop(component, property_name) == value:
        return component
    for child in _children(component):
        if isinstance(child, Component):
            match = _find(child, property_name=property_name, value=value)
            if match is not None:
                return match
    return None


def _children(component: Component) -> list[object]:
    value = getattr(component, 'children', None)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _prop(component: Component, name: str):
    return getattr(component, name, None)
