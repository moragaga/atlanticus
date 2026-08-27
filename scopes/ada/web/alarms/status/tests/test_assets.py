from importlib.resources import files

from ada.web.alarms import status


def test_alarm_status_css_is_packaged() -> None:
    package = files(status)
    css_list = (package / 'resources/css/css.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['10-alarm-status.css']
    css = (package / 'resources/css/10-alarm-status.css').read_text(encoding='utf-8')
    assert '.ada-alarm-status__action' in css
    assert ':focus-visible' in css
