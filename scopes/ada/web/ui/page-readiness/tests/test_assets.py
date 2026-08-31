from __future__ import annotations

from importlib.resources import files


def test_asset_lists_publish_generic_css_and_runtime() -> None:
    package = files('ada.web.ui.page_readiness')
    css_list = package.joinpath('resources/css/css.list').read_text().splitlines()
    js_list = package.joinpath('resources/js/js.list').read_text().splitlines()

    assert css_list == ['10-page-readiness.css']
    assert js_list == ['10-page-readiness.js']


def test_runtime_uses_contractual_markers_and_no_tool_specific_state() -> None:
    package = files('ada.web.ui.page_readiness')
    js = package.joinpath('resources/js/10-page-readiness.js').read_text()

    for token in (
        'data-ada-page-readiness',
        'data-ada-component-key',
        'data-ada-render-ready',
        'MutationObserver',
        'transitionend',
        'requestAnimationFrame',
    ):
        assert token in js

    assert 'data-ada-render-key' not in js

    for token in (
        'Integrated Operations',
        'Flotación',
        'Carguío',
        'localStorage',
        'sessionStorage',
        'fetch(',
        'setInterval(',
    ):
        assert token not in js
