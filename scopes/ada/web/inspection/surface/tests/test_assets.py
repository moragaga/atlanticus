from importlib.resources import files


def _resource(kind: str, name: str) -> str:
    return (
        files('ada.web.inspection.surface')
        .joinpath('resources', kind, name)
        .read_text(encoding='utf-8')
    )


def test_surface_assets_are_packaged_in_explicit_order() -> None:
    package = files('ada.web.inspection.surface').joinpath('resources')

    assert package.joinpath('css', 'css.list').read_text(encoding='utf-8').splitlines() == [
        '10-kpi-inspection-surface.css'
    ]
    assert package.joinpath('js', 'js.list').read_text(encoding='utf-8').splitlines() == [
        '10-kpi-inspection-surface.js'
    ]


def test_css_defines_click_opt_in_and_bottom_offcanvas_without_hover_activation() -> None:
    css = _resource('css', '10-kpi-inspection-surface.css')

    assert '[data-kpi-inspection-key] {' in css
    assert 'cursor: help;' in css
    assert 'position: fixed;' in css
    assert 'bottom: 0;' in css
    assert 'transform: translateY(105%);' in css
    assert "[data-open='true']" in css


def test_javascript_uses_event_delegation_and_never_hover_handlers() -> None:
    javascript = _resource('js', '10-kpi-inspection-surface.js')

    assert "const TRIGGER_SELECTOR = '[data-kpi-inspection-key]'" in javascript
    assert "document.addEventListener('click', handleClick)" in javascript
    assert "document.addEventListener('keydown', handleKeydown)" in javascript
    assert '.closest?.(TRIGGER_SELECTOR)' in javascript
    assert "addEventListener('mouseover'" not in javascript
    assert "addEventListener('mouseenter'" not in javascript


def test_javascript_reads_memory_api_safely_and_handles_races() -> None:
    javascript = _resource('js', '10-kpi-inspection-surface.js')

    assert 'new AbortController()' in javascript
    assert 'encodeURIComponent(kpiKey)' in javascript
    assert "cache: 'no-store'" in javascript
    assert 'requestSequence' in javascript
    assert "setState('unavailable')" in javascript
    assert "setState('ready')" in javascript
    assert "setState('error')" in javascript


def test_javascript_renders_definition_as_text_not_html() -> None:
    javascript = _resource('js', '10-kpi-inspection-surface.js')

    assert '.textContent =' in javascript
    assert 'replaceChildren()' in javascript
    assert '.innerHTML' not in javascript
    assert 'document.createElement(' in javascript


def test_javascript_keeps_surface_independent_from_dash_rerenders() -> None:
    javascript = _resource('js', '10-kpi-inspection-surface.js')

    assert 'MutationObserver' not in javascript
    assert 'dash_clientside' not in javascript
    assert 'document.getElementById(ROOT_ID)' in javascript
    assert "document.addEventListener('DOMContentLoaded', initialize" in javascript
