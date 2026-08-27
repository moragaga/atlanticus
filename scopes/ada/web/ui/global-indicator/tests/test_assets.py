from importlib.resources import files


def test_global_indicator_css_is_packaged_and_preserves_layout_contract() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    css = css_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-global-indicator.css']
    assert 'flex: 1 1 0;' in css
    assert 'min-height: 5.5rem;' in css
    assert '.global-indicator__row--empty' in css
    assert '.global-indicator__last-measurement--empty' in css
    assert 'visibility: hidden;' in css


def test_global_indicator_desktop_layout_uses_equal_columns_and_natural_content_width() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    css = css_root.joinpath('10-global-indicator.css').read_text(encoding='utf-8')

    assert 'grid-auto-columns: minmax(0, 1fr);' in css
    assert 'grid-auto-flow: column;' in css
    assert 'width: auto;' in css
    assert 'max-width: 100%;' in css
    assert 'text-overflow: ellipsis;' in css
    assert 'table-layout: auto;' in css
