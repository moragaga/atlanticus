from importlib.resources import files


def test_time_status_css_is_packaged_without_freezing_preventive_visuals() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    css = css_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-time-status.css']
    assert "[data-ada-time-status-detail-trigger='true']" in css
    assert 'user-select: none;' in css
    assert '.ada-time-status__source-content--data_error' in css
    assert '.ada-time-status__source-content--hard_stale' in css
    assert '@keyframes' not in css
