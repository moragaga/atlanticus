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
    assert '--ada-time-status-detail-gap: .2rem;' in surface
    assert 'top: calc(100% + var(--ada-time-status-detail-gap));' in surface
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


def test_time_status_css_maps_preventive_to_stronger_pulse_and_hard_stale_to_solid_alert() -> None:
    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )

    assert '.ada-time-status__source-content--preventive {' in css
    assert 'animation: ada-time-status-preventive-pulse 1.35s ease-in-out infinite;' in css
    assert 'opacity: .62;' in css
    assert '.ada-time-status__source-content--hard_stale,' in css
    assert '.ada-time-status__source-content--data_error {' in css
    assert 'background: #c82333;' in css
    assert 'color: var(--ada-color-text-inverse);' in css


def test_detail_surface_css_supports_flip_shift_and_viewport_bounded_height() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    css = css_root.joinpath('10-time-status.css').read_text(encoding='utf-8')
    surface = css.split('.ada-time-status-detail {', 1)[1].split('}', 1)[0]

    assert '--ada-time-status-detail-shift-x: 0px;' in surface
    assert '--ada-time-status-detail-available-height:' in surface
    assert '--ada-time-status-detail-viewport-width:' in surface
    assert 'box-sizing: border-box;' in surface
    assert 'transform: translateX(var(--ada-time-status-detail-shift-x));' in surface
    assert 'var(--ada-time-status-detail-available-height)' in surface
    assert "[data-ada-time-status-detail-placement='top']" in css
    top_surface = css.split(
        ".ada-time-status-detail[data-ada-time-status-detail-placement='top'] {", 1
    )[1].split('}', 1)[0]
    assert 'top: auto;' in top_surface
    assert 'bottom: calc(100% + var(--ada-time-status-detail-gap));' in top_surface
    assert 'position: fixed;' not in surface


def test_detail_surface_mobile_contract_uses_full_usable_viewport_without_modal_layout() -> None:
    css_root = files('ada.web.ui.time_status').joinpath('resources/css')
    css = css_root.joinpath('10-time-status.css').read_text(encoding='utf-8')
    mobile = css.split('@media (max-width: 767.98px) {')[-1]

    assert '.ada-time-status-detail {' in mobile
    assert 'width: var(--ada-time-status-detail-viewport-width);' in mobile
    assert 'max-width: var(--ada-time-status-detail-viewport-width);' in mobile
    assert '.ada-time-status-detail__content {' in mobile
    assert 'min-width: 0;' in mobile
    assert 'position: fixed;' not in mobile
    assert 'backdrop' not in mobile.lower()


def test_detail_controller_positions_open_surface_against_visual_viewport_and_reflows_never() -> (
    None
):
    js_root = files('ada.web.ui.time_status').joinpath('resources/js')
    javascript = js_root.joinpath('20-time-status-detail.js').read_text(encoding='utf-8')

    assert "const PLACEMENT_ATTRIBUTE = 'data-ada-time-status-detail-placement'" in javascript
    assert 'const VIEWPORT_MARGIN_PX = 8' in javascript
    assert 'window.visualViewport' in javascript
    assert 'parts.trigger.getBoundingClientRect()' in javascript
    assert 'parts.surface.scrollHeight' in javascript
    assert "? 'bottom' : 'top'" in javascript
    assert 'parts.surface.setAttribute(PLACEMENT_ATTRIBUTE, placement)' in javascript
    assert "'--ada-time-status-detail-available-height'" in javascript
    assert "'--ada-time-status-detail-viewport-width'" in javascript
    assert "'--ada-time-status-detail-shift-x'" in javascript
    assert 'parts.surface.getBoundingClientRect()' in javascript
    assert 'window.requestAnimationFrame' in javascript
    assert "window.addEventListener('resize', schedulePositionOpen)" in javascript
    assert "window.addEventListener('scroll', schedulePositionOpen, true)" in javascript
    assert "window.visualViewport.addEventListener('resize', schedulePositionOpen)" in javascript
    assert "window.visualViewport.addEventListener('scroll', schedulePositionOpen)" in javascript
    assert 'position: fixed' not in javascript
    assert 'document.body.appendChild' not in javascript
    assert 'ResizeObserver' not in javascript


def test_ts012b_visual_polish_uses_bar_surface_hover_only_affordance_and_compact_clock() -> None:
    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )
    surface = css.split('.ada-time-status-detail {', 1)[1].split('}', 1)[0]
    sources = css.split('.ada-time-status__sources {', 1)[1].split('}', 1)[0]
    hover = css.split(
        ".ada-time-status__sources[data-ada-time-status-detail-trigger='true']:hover {", 1
    )[1].split('}', 1)[0]
    datetime = css.split('.ada-time-status__timestamp--datetime {', 1)[1].split('}', 1)[0]

    assert 'inset-inline-start: 0;' in surface
    assert 'background: var(--ada-operational-header-surface' in surface
    assert 'color: var(--ada-color-text-primary);' in surface
    assert 'background: var(--ada-color-surface-strong);' not in surface
    assert 'width: fit-content;' in sources
    assert 'border: 1px solid transparent;' in sources
    assert 'border-color: var(--ada-color-border-primary);' in hover
    assert 'min-width: 0;' in datetime
    assert 'text-align: start;' in datetime
    assert '.ada-time-status-detail__empty {' in css
    assert '.ada-time-status-detail__heading {' in css


def test_clock_hydrates_new_time_status_nodes_immediately_after_dash_rerender() -> None:
    javascript = (
        files('ada.web.ui.time_status')
        .joinpath('resources/js/10-time-status-clock.js')
        .read_text(encoding='utf-8')
    )

    assert 'new MutationObserver(handleMutations)' in javascript
    assert (
        'controller.observer.observe(document.body, { childList: true, subtree: true })'
        in javascript
    )
    assert 'syncAddedElement(node, nowMs, text)' in javascript
    assert 'element.querySelectorAll(CLOCK_SELECTOR)' in javascript
    assert 'element.querySelectorAll(SUMMARY_SELECTOR)' in javascript
    assert 'setInterval' not in javascript


def test_clock_publishes_neutral_source_freshness_events_without_component_knowledge() -> None:
    javascript = (
        files('ada.web.ui.time_status')
        .joinpath('resources/js/10-time-status-clock.js')
        .read_text(encoding='utf-8')
    )

    assert "SOURCE_FRESHNESS_EVENT = 'ada:source-freshness'" in javascript
    assert "SOURCE_FRESHNESS_REQUEST_EVENT = 'ada:source-freshness-request'" in javascript
    assert 'new CustomEvent(SOURCE_FRESHNESS_EVENT' in javascript
    assert 'detail: { toolKey, sourceKey, condition }' in javascript
    assert "publishSourceFreshness(source, 'data_error')" in javascript
    assert 'publishSourceFreshness(source, condition, true)' in javascript
    assert 'document.addEventListener(SOURCE_FRESHNESS_REQUEST_EVENT' in javascript
    assert 'component_key' not in javascript
    assert 'global_indicators' not in javascript


def test_responsive_time_summary_stacks_rows_below_1280_without_stacking_row_content() -> None:
    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )
    responsive = css.split('@media only screen and (max-width: 1279.98px) {', 1)[1].split(
        '@media (max-width: 767.98px) {', 1
    )[0]

    assert '.ada-time-status,\n    .ada-time-status__sources {' in responsive
    assert 'flex-direction: column;' in responsive
    assert '.ada-time-status__source,\n    .ada-time-status__current {' in responsive
    assert 'width: 100%;' in responsive
    assert '.ada-time-status__source--divided {' in responsive
    assert 'border-inline-end: 0;' in responsive
    assert '.ada-time-status__current {' in responsive
    assert 'justify-content: flex-start;' in responsive
    assert '.ada-time-status__source-content {' not in responsive
    assert '.ada-time-status__current-content {' not in responsive
    assert 'font-size:' not in responsive


def test_responsive_time_summary_keeps_hidden_detail_trigger_compact_and_desktop_unchanged() -> (
    None
):
    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )
    responsive = css.split('@media only screen and (max-width: 1279.98px) {', 1)[1].split(
        '@media (max-width: 767.98px) {', 1
    )[0]
    desktop = css.split('@media only screen and (min-width: 1280px) {', 1)[1].split(
        '@media only screen and (max-width: 1279.98px) {', 1
    )[0]

    assert ".ada-time-status__sources[data-ada-time-status-detail-trigger='true'] {" in responsive
    assert 'width: fit-content;' in responsive
    assert 'max-width: 100%;' in responsive
    assert '::before' not in responsive
    assert '::after' not in responsive
    assert 'font-size: .6rem;' in desktop
    assert 'flex-direction: column;' not in desktop


def test_responsive_time_mobile_detail_contract_remains_scoped_to_767() -> None:
    css = (
        files('ada.web.ui.time_status')
        .joinpath('resources/css/10-time-status.css')
        .read_text(encoding='utf-8')
    )
    mobile_detail = css.split('@media (max-width: 767.98px) {', 1)[1]

    assert '.ada-time-status-detail {' in mobile_detail
    assert 'width: var(--ada-time-status-detail-viewport-width);' in mobile_detail
    assert '.ada-time-status-detail__source {' in mobile_detail
    assert 'grid-template-columns: 1fr;' in mobile_detail
    assert '.ada-time-status,\n    .ada-time-status__sources {' not in mobile_detail
