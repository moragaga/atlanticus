from importlib.resources import files


def test_time_status_css_is_packaged_with_control_source_freshness_visuals() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    entries = css_root.joinpath('css.list').read_text(encoding='utf-8').splitlines()
    css = css_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-time-status.css']
    assert "[data-ada-time-status-detail-trigger='true']" in css
    assert 'user-select: none;' in css
    assert '.ada-time-status__source-content--data_error' in css
    assert '.ada-time-status__source-content--hard_stale' in css
    assert '@keyframes ada-time-status-preventive-pulse' in css


def test_anchored_detail_surface_is_local_absolute_and_non_modal() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    css = css_root.joinpath('10-time-status.css').read_text(encoding='utf-8')
    surface = css.split('.ada-time-status-detail {', 1)[1].split('}', 1)[0]

    assert '.ada-time-status-container {' in css
    assert 'position: relative;' in css.split('.ada-time-status-container {', 1)[1].split('}', 1)[0]
    assert 'position: absolute;' in surface
    assert 'top: calc(100% + .25rem);' in surface
    assert 'position: fixed;' not in surface
    assert 'inset: 0;' not in surface
    assert 'backdrop' not in css.lower()


def test_real_clock_asset_is_packaged_and_uses_real_time_resynchronization() -> None:
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    entries = js_root.joinpath('js.list').read_text(encoding='utf-8').splitlines()
    javascript = js_root.joinpath(entries[0]).read_text(encoding='utf-8')

    assert entries == ['10-time-status-clock.js', '20-time-status-detail.js']
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


def test_detail_controller_is_packaged_after_clock_and_uses_local_dom_boundaries() -> None:
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    entries = js_root.joinpath('js.list').read_text(encoding='utf-8').splitlines()
    javascript = js_root.joinpath('20-time-status-detail.js').read_text(encoding='utf-8')

    assert entries == ['10-time-status-clock.js', '20-time-status-detail.js']
    assert 'const CONTAINER_SELECTOR = "[data-ada-time-status-container=\'true\']"' in javascript
    assert 'const TRIGGER_SELECTOR = "[data-ada-time-status-detail-trigger=\'true\']"' in javascript
    assert 'const SURFACE_SELECTOR = "[data-ada-time-status-detail-surface=\'true\']"' in javascript
    assert 'trigger.closest(CONTAINER_SELECTOR)' in javascript
    assert 'container.querySelector(SURFACE_SELECTOR)' in javascript
    assert 'document.getElementById' not in javascript
    assert 'localStorage' not in javascript
    assert 'sessionStorage' not in javascript
    assert 'dash_clientside' not in javascript


def test_detail_controller_supports_toggle_outside_escape_and_keyboard_without_hover() -> None:
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    javascript = js_root.joinpath('20-time-status-detail.js').read_text(encoding='utf-8')

    assert "document.addEventListener('click', handleClick)" in javascript
    assert "document.addEventListener('keydown', handleKeydown)" in javascript
    assert "event.key === 'Escape'" in javascript
    assert "event.key !== 'Enter' && event.key !== ' '" in javascript
    assert 'event.preventDefault()' in javascript
    assert 'parts.surface.hidden = !isOpen' in javascript
    assert "parts.trigger.setAttribute('aria-expanded'" in javascript
    assert "parts.surface.setAttribute('aria-hidden'" in javascript
    assert '!container.contains(event.target)' in javascript
    assert "addEventListener('mouseover'" not in javascript
    assert "addEventListener('mouseenter'" not in javascript
    assert 'MutationObserver' in javascript
    assert "const TOOL_KEY_ATTRIBUTE = 'data-ada-time-status-tool-key'" in javascript
    assert 'let openToolKey = null' in javascript
    assert 'mutation.addedNodes.forEach(restoreAddedNode)' in javascript
    assert 'observer.observe(document.body, { childList: true, subtree: true })' in javascript


def test_dynamic_detail_rows_are_neutral_and_do_not_define_health_visuals() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    css = css_root.joinpath('10-time-status.css').read_text(encoding='utf-8')
    detail_css = css.split('.ada-time-status-detail__content {', 1)[1]

    assert '.ada-time-status-detail__source {' in detail_css
    assert '.ada-time-status-detail__source-value {' in detail_css
    assert '[data-source-role=' not in detail_css
    assert '@keyframes' not in detail_css
    assert 'animation:' not in detail_css


def test_clock_asset_recomputes_control_source_freshness_on_real_time_ticks() -> None:
    from importlib.resources import files

    asset = (
        files('ada.web.ui.time_status')
        .joinpath('resources/js/10-time-status-clock.js')
        .read_text(encoding='utf-8')
    )

    assert 'SOURCE_SELECTOR = "[data-ada-time-status-source=\'true\']"' in asset
    assert 'formatRelativeAge' in asset
    assert 'resolveCondition' in asset
    assert "condition === 'hard_stale'" in asset
    assert "source.getAttribute('data-source-condition') === 'data_error'" in asset
    assert 'Math.max(0, Math.floor((nowMs - timestampMs) / 1000))' in asset
    assert "summary.setAttribute('data-content-stale', contentStale ? 'true' : 'false')" in asset
    assert "summary.setAttribute('data-has-data-error', hasDataError ? 'true' : 'false')" in asset


def test_time_status_css_maps_preventive_to_pulse_and_hard_stale_to_solid_alert() -> None:
    from importlib.resources import files

    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )

    assert "[data-source-condition='preventive']" in css
    assert 'ada-time-status-preventive-pulse' in css
    assert "[data-source-condition='hard_stale']" in css
    assert "[data-source-condition='data_error']" in css
