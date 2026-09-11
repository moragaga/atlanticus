from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable


def _asset_names(root: Traversable, suffix: str) -> set[str]:
    return {
        entry.name for entry in root.iterdir() if entry.is_file() and entry.name.endswith(suffix)
    }


def test_asset_lists_publish_generic_css_and_runtime() -> None:
    package = files('ada.web.ui.page_readiness').joinpath('resources')
    css_root = package.joinpath('css')
    js_root = package.joinpath('js')
    css_list = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    js_list = js_root.joinpath('js.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['10-page-readiness.css']
    assert js_list == ['10-page-readiness.js']
    assert all(css_root.joinpath(name).is_file() for name in css_list)
    assert all(js_root.joinpath(name).is_file() for name in js_list)
    assert _asset_names(css_root, '.css') == set(css_list)
    assert _asset_names(js_root, '.js') == set(js_list)
