from importlib.resources import files
from importlib.resources.abc import Traversable


def _asset_names(root: Traversable, suffix: str) -> set[str]:
    return {
        entry.name for entry in root.iterdir() if entry.is_file() and entry.name.endswith(suffix)
    }


def test_surface_assets_are_packaged_in_explicit_order() -> None:
    package = files('ada.web.inspection.surface').joinpath('resources')
    css_root = package.joinpath('css')
    js_root = package.joinpath('js')
    css_list = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    js_list = js_root.joinpath('js.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['10-kpi-inspection-surface.css']
    assert js_list == ['10-kpi-inspection-surface.js']
    assert all(css_root.joinpath(name).is_file() for name in css_list)
    assert all(js_root.joinpath(name).is_file() for name in js_list)
    assert _asset_names(css_root, '.css') == set(css_list)
    assert _asset_names(js_root, '.js') == set(js_list)
