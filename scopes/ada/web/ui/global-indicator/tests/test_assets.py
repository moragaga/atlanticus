from importlib.resources import files


def test_global_indicator_css_is_packaged() -> None:
    css_root = files('ada.web.ui.global_indicator').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    css_path = css_root.joinpath('10-global-indicator.css')

    assert entries == ['10-global-indicator.css']
    assert css_path.is_file()
    assert css_path.read_text(encoding='utf-8').strip()
