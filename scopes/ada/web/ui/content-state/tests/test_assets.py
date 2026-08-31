from importlib.resources import files


def test_content_state_css_is_packaged_and_ordered() -> None:
    package = files('ada.web.ui.content_state')
    css_list = package.joinpath('resources/css/css.list').read_text(encoding='utf-8').splitlines()
    css = package.joinpath('resources/css/10-content-state.css')

    assert css_list == ['10-content-state.css']
    assert css.is_file()


def test_overlay_is_absolute_visual_mark_that_never_blocks_interaction() -> None:
    css = (
        files('ada.web.ui.content_state')
        .joinpath('resources/css/10-content-state.css')
        .read_text(encoding='utf-8')
    )

    assert 'position: absolute;' in css
    assert 'inset: 0;' in css
    assert 'pointer-events: none;' in css
    assert 'pointer-events: auto;' not in css
    assert 'backdrop-filter: grayscale(1);' in css


def test_css_maps_each_degraded_state_to_one_visible_view() -> None:
    css = (
        files('ada.web.ui.content_state')
        .joinpath('resources/css/10-content-state.css')
        .read_text(encoding='utf-8')
    )

    for state in ('stale', 'source_error', 'construction'):
        assert f"[data-ada-content-state='{state}']" in css
        assert f"[data-ada-content-state-view='{state}']" in css

    assert '.ada-content-state__view {' in css
    assert 'display: none;' in css


def test_content_state_runtime_js_is_packaged_and_uses_neutral_freshness_event() -> None:
    package = files('ada.web.ui.content_state')
    js_list = package.joinpath('resources/js/js.list').read_text(encoding='utf-8').splitlines()
    javascript = package.joinpath('resources/js/20-content-state-runtime.js').read_text(
        encoding='utf-8'
    )

    assert js_list == ['20-content-state-runtime.js']
    assert "SOURCE_FRESHNESS_EVENT = 'ada:source-freshness'" in javascript
    assert "SOURCE_FRESHNESS_REQUEST_EVENT = 'ada:source-freshness-request'" in javascript
    assert 'document.dispatchEvent(new CustomEvent(SOURCE_FRESHNESS_REQUEST_EVENT))' in javascript
    assert "[data-ada-content-state-runtime='true']" in javascript
    assert 'data-ada-time-status' not in javascript
    assert 'global_indicators' not in javascript
    assert 'MutationObserver' in javascript
    assert 'source_error: 2' in javascript
    assert 'construction: 3' in javascript
    assert 'setInterval' not in javascript
    assert 'setTimeout' not in javascript
    assert 'innerHTML' not in javascript
    assert 'replaceChild' not in javascript


def test_authoring_css_suppresses_overlay_without_rewriting_content_state() -> None:
    css = (
        files('ada.web.ui.content_state')
        .joinpath('resources/css/10-content-state.css')
        .read_text(encoding='utf-8')
    )

    assert "[data-ada-content-state-presentation='authoring']" in css
    assert 'opacity: 0;' in css
    assert 'visibility: hidden;' in css
    assert (
        "data-ada-content-state='ready'"
        not in css.split("[data-ada-content-state-presentation='authoring']", maxsplit=1)[1].split(
            '}', maxsplit=1
        )[0]
    )


def test_runtime_js_keeps_authoring_overlay_accessibility_hidden() -> None:
    javascript = (
        files('ada.web.ui.content_state')
        .joinpath('resources/js/20-content-state-runtime.js')
        .read_text(encoding='utf-8')
    )

    assert "PRESENTATION_ATTRIBUTE = 'data-ada-content-state-presentation'" in javascript
    assert 'overlaySuppressed(wrapper)' in javascript
    assert "=== 'authoring'" in javascript
