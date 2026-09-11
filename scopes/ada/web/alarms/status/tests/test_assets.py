from importlib.resources import files

from ada.web.alarms import status


def test_alarm_status_css_is_packaged() -> None:
    package = files(status)
    css_list = (package / 'resources/css/css.list').read_text(encoding='utf-8').splitlines()
    css_path = package / 'resources/css/10-alarm-status.css'

    assert css_list == ['10-alarm-status.css']
    assert css_path.is_file()
    assert css_path.read_text(encoding='utf-8').strip()
