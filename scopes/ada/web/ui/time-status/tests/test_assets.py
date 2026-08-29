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


def test_real_clock_asset_is_packaged_and_uses_real_time_resynchronization() -> None:
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    entries = js_root.joinpath('js.list').read_text(encoding='utf-8').splitlines()
    javascript = js_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-time-status-clock.js']
    assert 'Date.now()' in javascript
    assert 'new Date(epochMs)' in javascript
    assert 'window.setTimeout(scheduleNextTick, delayMs)' in javascript
    assert '1000 - (nowMs % 1000)' in javascript
    assert "document.addEventListener('visibilitychange'" in javascript
    assert "window.addEventListener('focus', resync)" in javascript
    assert "window.addEventListener('pageshow', resync)" in javascript
    assert 'document.querySelectorAll(CLOCK_SELECTOR)' in javascript
    assert 'setInterval' not in javascript
    assert 'seconds +=' not in javascript


def test_real_clock_asset_reads_time_zone_from_runtime_config() -> None:
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    javascript = js_root.joinpath('10-time-status-clock.js').read_text(encoding='utf-8')

    assert "const MODULE_NAME = 'ada-time-status'" in javascript
    assert "const DEFAULT_TIME_ZONE = 'America/Santiago'" in javascript
    assert 'runtimeConfig()?.modules?.[MODULE_NAME]?.time_zone' in javascript
    assert "hourCycle: 'h23'" in javascript
    assert '${values.year}-${values.month}-${values.day}' in javascript
