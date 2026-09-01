from importlib.resources import files


def test_global_indicator_css_is_packaged_and_preserves_layout_contract() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    css = css_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-global-indicator.css']
    assert 'flex: 0 0 100%;' in css
    assert 'min-height: 4.25rem;' in css
    assert 'min-height: 5.5rem;' not in css
    assert '.global-indicator__row--empty' not in css
    assert '.global-indicator__last-measurement--empty' not in css
    assert 'visibility: hidden;' not in css
    assert 'border-left: 1px solid var(--global-indicator-border);' not in css
    assert 'width: 3.25rem;' not in css
    assert 'user-select: none;' in css
    assert 'padding: .3rem .55rem .3rem 0;' in css


def test_global_indicator_desktop_layout_uses_equal_columns_and_natural_content_width() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    css = css_root.joinpath('10-global-indicator.css').read_text(encoding='utf-8')

    assert 'grid-auto-columns: minmax(0, 1fr);' in css
    assert 'grid-auto-flow: column;' in css
    assert 'width: auto;' in css
    assert 'max-width: 100%;' in css
    assert 'text-overflow: ellipsis;' in css
    assert 'table-layout: auto;' in css


def test_global_indicator_mobile_layout_uses_two_columns_and_centers_odd_tail() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    css = css_root.joinpath('10-global-indicator.css').read_text(encoding='utf-8')

    mobile = css.split('@media only screen and (min-width: 350px) {', 1)[1].split(
        '@media only screen and (min-width: 480px)', 1
    )[0]
    assert 'flex: 0 0 50%;' in mobile
    assert 'max-width: 50%;' in mobile
    assert '.global-indicators > .global-indicator:last-child:nth-child(odd)' in mobile
    assert 'margin-inline: auto;' in mobile


def test_global_indicator_switches_to_single_row_at_tablet_pelambres() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    css = css_root.joinpath('10-global-indicator.css').read_text(encoding='utf-8')

    tablet = css.split('@media only screen and (min-width: 1280px) {', 1)[1].split(
        '@media only screen and (min-width: 1366px)', 1
    )[0]
    assert 'display: grid;' in tablet
    assert 'grid-auto-flow: column;' in tablet
    assert 'grid-auto-columns: minmax(0, 1fr);' in tablet
    assert 'min-height: 0;' in tablet


def test_global_indicator_visual_calibration_scales_mobile_tablet_and_videowall() -> None:
    css = (
        files('ada.web.ui.global_indicator')
        .joinpath('resources/css/10-global-indicator.css')
        .read_text(encoding='utf-8')
    )

    assert '.font-size-gi-100 { font-size: .8rem; }' in css
    assert '.font-size-gi-100 { font-size: .72rem; }' in css
    assert '.font-size-gi-100 { font-size: .92rem; }' in css
    assert 'row-gap: .45rem;' in css
    assert 'padding-block: .38rem .55rem;' in css
    assert '.global-indicator__label,\n    .global-indicator__unit { font-size: .86rem; }' in css
    assert 'padding-inline-end: 1rem;' in css
