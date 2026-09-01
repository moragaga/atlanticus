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
    time_status = html.Div('time', id='time-status-component')
    desktop = html.Button('desktop', id='desktop-navigation')
    mobile = html.Button('mobile', id='mobile-navigation')

    component = build_ada_operational_header(
        brand=brand,
        global_indicators=indicators,
        alarm_management=management,
        alarm_status=status,
        time_status=time_status,
        desktop_navigation_trigger=desktop,
        mobile_navigation_trigger=mobile,
    )

    assert _prop(component, 'data-ada-component-key') == 'operational_header'
    assert _require_slot(component, 'brand') is not None
    assert _require_slot(component, 'global_indicators') is not None
    assert _require_slot(component, 'alarm_management') is not None
    assert _require_slot(component, 'alarm_status') is not None
    assert _require_slot(component, 'time_status') is not None
    assert _require_slot(component, 'navigation_desktop') is not None
    assert _require_slot(component, 'navigation_mobile') is not None
    assert _require_id(component, 'brand-component') is brand
    assert _require_id(component, 'indicators-component') is indicators
    assert _require_id(component, 'management-component') is management
    assert _require_id(component, 'status-component') is status
    assert _require_id(component, 'time-status-component') is time_status
    assert _require_id(component, 'desktop-navigation') is desktop
    assert _require_id(component, 'mobile-navigation') is mobile


def test_optional_operational_slots_are_empty_without_placeholders() -> None:
    component = build_ada_operational_header(brand=html.Div('brand'))

    for slot_key in ('global_indicators', 'alarm_management', 'alarm_status', 'time_status'):
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

    tablet = _media_section(css, 1280, 1366)
    global_slot = _css_rule(tablet, '.ada-operational-header__global-indicators-slot')
    management_slot = _css_rule(tablet, '.ada-operational-header__alarm-management-slot')
    status_slot = _css_rule(tablet, '.ada-operational-header__alarm-status-slot')

    assert 'flex: 1 1 0;' in global_slot
    assert 'width: 8.2rem;' in management_slot
    assert 'flex: 0 1 8.2rem;' in management_slot
    assert 'width: 7.4rem;' in status_slot
    assert 'flex: 0 1 7.4rem;' in status_slot


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


def _css_rules(css: str, selector: str) -> tuple[str, ...]:
    marker = f'{selector} {{'
    matches = css.split(marker)[1:]
    if not matches:
        raise AssertionError(f'CSS rule {selector!r} was not found')
    return tuple(match.split('}', 1)[0] for match in matches)


def _css_rule(css: str, selector: str) -> str:
    return _css_rules(css, selector)[-1]


def _media_section(css: str, width: int, next_width: int | None = None) -> str:
    marker = f'@media only screen and (min-width: {width}px) {{'
    if marker not in css:
        raise AssertionError(f'Media query {width}px was not found')
    section = css.split(marker, 1)[1]
    if next_width is not None:
        next_marker = f'@media only screen and (min-width: {next_width}px)'
        section = section.split(next_marker, 1)[0]
    return section


def test_header_desktop_calibration_gives_remaining_width_to_global_indicators() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    desktop = _media_section(css, 1920, 2560)
    brand_slot = _css_rule(desktop, '.ada-operational-header__brand-slot')
    management_slot = _css_rule(desktop, '.ada-operational-header__alarm-management-slot')
    status_slot = _css_rule(desktop, '.ada-operational-header__alarm-status-slot')

    assert '--ada-operational-header-brand-width: 12rem;' in css
    assert '--ada-operational-header-management-width: 10.5rem;' in css
    assert '--ada-operational-header-status-width: 9.75rem;' in css
    assert 'width: 10.25rem;' in brand_slot
    assert 'flex-basis: 10.25rem;' in brand_slot
    assert 'width: 9.1rem;' in management_slot
    assert 'flex-basis: 9.1rem;' in management_slot
    assert 'width: 8.2rem;' in status_slot
    assert 'flex-basis: 8.2rem;' in status_slot


def test_time_status_slot_sits_below_primary_header_row() -> None:
    time_status = html.Div('time', id='time-status')
    component = build_ada_operational_header(
        brand=html.Div('brand'),
        time_status=time_status,
        desktop_navigation_trigger=html.Button('menu'),
    )

    children = _children(component)
    assert len(children) == 2
    primary, time_slot = children
    assert 'ada-operational-header__primary' in (_prop(primary, 'className') or '')
    assert 'ada-navigation__anchor-host' in (_prop(primary, 'className') or '')
    assert _prop(time_slot, 'data-ada-slot-key') == 'time_status'
    assert _prop(time_slot, 'data-slot-empty') == 'false'
    assert _require_id(time_slot, 'time-status') is time_status


def test_header_css_keeps_time_status_out_of_primary_row_geometry() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    assert '.ada-operational-header__time-status-slot {' in css
    assert 'min-height: 1.35rem;' in css
    assert 'padding: .02rem .6rem .04rem;' in css
    assert 'overflow: visible;' in css
    assert '.ada-operational-header__primary {' in css


def test_header_responsive_contract_uses_pelambres_breakpoints() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    for width in (350, 480, 1280, 1366, 1536, 1920, 2560):
        assert f'@media only screen and (min-width: {width}px)' in css
    assert '@media (min-width: 1024px)' not in css
    assert '@media (min-width: 992px)' not in css


def test_header_mobile_keeps_brand_menu_indicators_management_and_status_visible() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    mobile = css.split('@media only screen and (min-width: 1280px) {', 1)[0]
    global_slot = '\n'.join(_css_rules(mobile, '.ada-operational-header__global-indicators-slot'))
    management_slot = '\n'.join(
        _css_rules(mobile, '.ada-operational-header__alarm-management-slot')
    )
    status_slot = '\n'.join(_css_rules(mobile, '.ada-operational-header__alarm-status-slot'))
    mobile_navigation = '\n'.join(_css_rules(mobile, '.ada-operational-header__mobile-navigation'))

    assert 'grid-template-columns: minmax(0, 1fr);' in mobile
    assert '--ada-operational-header-mobile-menu-safe-area: 3.25rem;' in css
    assert 'position: absolute;' in mobile_navigation
    assert 'inset-inline-end: .45rem;' in mobile_navigation
    assert 'display: flex;' in global_slot
    assert 'grid-column: 1 / -1;' in global_slot
    assert 'display: flex;' in management_slot
    assert 'grid-column: 1 / -1;' in management_slot
    assert 'display: flex;' in status_slot
    assert 'grid-column: 1 / -1;' in status_slot
    assert 'display: flex;' in mobile_navigation
    assert 'justify-content: flex-end;' in mobile_navigation
    assert "[data-slot-empty='true']" in mobile
    assert 'row-gap: .35rem;' in mobile
    assert 'row-gap: .45rem;' in mobile


def test_header_tablet_pelambres_switches_to_compact_horizontal_geometry() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    tablet = css.split('@media only screen and (min-width: 1280px) {', 1)[1].split(
        '@media only screen and (min-width: 1366px)', 1
    )[0]
    assert 'display: flex;' in tablet
    assert 'height: 5rem;' in tablet
    assert '.ada-operational-header__mobile-navigation {\n        display: none;' in tablet
    assert '.ada-operational-header__desktop-navigation {\n        display: block;' in tablet


def test_header_desktop_keeps_same_geometry_and_scales_vertical_height() -> None:
    css = (
        files('ada.web.shell.header')
        .joinpath('resources/css/10-operational-header.css')
        .read_text(encoding='utf-8')
    )

    expected_heights = (
        (1366, 1536, '5.1rem'),
        (1536, 1920, '5.25rem'),
        (1920, 2560, '5.5rem'),
        (2560, None, '6.25rem'),
    )
    for width, next_width, height in expected_heights:
        section = _media_section(css, width, next_width)
        assert f'height: {height};' in section
        assert f'min-height: {height};' in section

    videowall = _media_section(css, 2560)
    assert '.ada-operational-header__desktop-navigation,' in videowall
    assert 'display: none;' in videowall
    assert 'width: 10.2rem;' in videowall
    assert 'width: 9.2rem;' in videowall
