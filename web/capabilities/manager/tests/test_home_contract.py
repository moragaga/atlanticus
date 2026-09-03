from dataclasses import fields
from pathlib import Path

from atlanticus.web.manager.models import ManagerSurfaceDefinition


def test_manager_surface_no_longer_has_default_module_contract() -> None:
    assert 'default_module_key' not in {field.name for field in fields(ManagerSurfaceDefinition)}


def test_home_is_a_static_surface_separate_from_module_content() -> None:
    layout = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/manager/web/layout.py'
    ).read_text(encoding='utf-8')
    callbacks = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/manager/web/callbacks.py'
    ).read_text(encoding='utf-8')

    assert 'children=build_manager_home(' in layout
    assert 'id=HOME_ID' in layout
    assert "Output(HOME_ID, 'hidden')" in callbacks
    assert "Output(CONTENT_ID, 'hidden')" in callbacks
    assert 'home_active = current_path == registry.root_route' in callbacks
    assert 'definition.default_module_key' not in callbacks


def test_module_pages_expose_explicit_manager_home_return() -> None:
    source = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/manager/web/callbacks.py'
    ).read_text(encoding='utf-8')

    assert 'build_manager_home_return(registry.root_route)' in source
    assert 'pathname or registry.root_route' in source


def test_summary_is_only_visible_on_manager_home() -> None:
    source = (
        Path(__file__).parents[1]
        / 'src/atlanticus/web/manager/web/callbacks.py'
    ).read_text(encoding='utf-8')

    assert "Output(SUMMARY_ID, 'hidden')" in source
    assert 'return not home_active, not home_active, home_active' in source


def test_home_css_is_an_isolated_asset_layer() -> None:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/manager/resources/css'
    css_list = (root / 'css.list').read_text(encoding='utf-8').splitlines()
    home = (root / '20_home.css').read_text(encoding='utf-8')

    assert css_list == [
        '00_tokens.css',
        '10_manager.css',
        '20_home.css',
        '30_visual_normalization.css',
    ]
    assert 'grid-template-columns: repeat(3, minmax(0, 1fr))' in home
    assert '@media (max-width: 1365px)' in home
    assert '@media (max-width: 767px)' in home
