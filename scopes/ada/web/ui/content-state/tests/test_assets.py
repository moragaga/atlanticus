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
