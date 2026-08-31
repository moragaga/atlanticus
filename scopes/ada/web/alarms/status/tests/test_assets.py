from importlib.resources import files

from ada.web.alarms import status


def test_alarm_status_css_is_packaged() -> None:
    package = files(status)
    css_list = (package / 'resources/css/css.list').read_text(encoding='utf-8').splitlines()

    assert css_list == ['10-alarm-status.css']
    css = (package / 'resources/css/10-alarm-status.css').read_text(encoding='utf-8')
    assert '.ada-alarm-status__action' in css
    assert ':focus-visible' in css
    assert '.ada-alarm-status:hover' in css
    assert '--ada-alarm-status-surface-hover:' in css
    assert '--ada-alarm-status-row-hover:' in css
    assert 'border-color: var(--ada-color-border-strong);' in css
    assert 'color: var(--ada-color-text-strong);' in css


def test_alarm_status_line_layout_is_flat_symmetric_and_hoverable() -> None:
    css_root = files('ada.web.alarms.status').joinpath('resources/css')
    css = css_root.joinpath('10-alarm-status.css').read_text(encoding='utf-8')

    assert 'grid-template-columns: 1.55rem minmax(0, 1fr);' in css
    assert '.ada-alarm-status__action + .ada-alarm-status__action' in css
    assert "content: '•';" in css
    assert 'border-right: 1px solid var(--ada-alarm-status-divider);' in css
    assert 'background: var(--ada-alarm-status-row-hover);' in css
    assert 'border-radius: 0;' in css
