(() => {
    'use strict';

    const DASHBOARD_SELECTOR = '[data-ada-module="dashboard"]';
    const TARGET_SELECTOR = '[data-ada-io-presentation-target]';
    const OVERVIEW_CONTROLS_SELECTOR = '.ada-io-dashboard__overview-controls';
    const BASELINE_SELECTOR = '.ada-alarm-baseline-surface';
    const BASELINE_POINT_SELECTOR = '.ada-alarm-baseline-surface__point';
    const VALID_PRESENTATIONS = new Set(['overview', 'mine', 'plant']);
    const TABLET_MIN_WIDTH = 1280;
    const DESKTOP_MIN_WIDTH = 1366;
    const VIDEOWALL_MIN_WIDTH = 2560;
    let resizeFrame = null;

    function resolveViewportMode(width) {
        if (width >= VIDEOWALL_MIN_WIDTH) {
            return 'videowall';
        }
        if (width >= DESKTOP_MIN_WIDTH) {
            return 'desktop';
        }
        if (width >= TABLET_MIN_WIDTH) {
            return 'tablet';
        }
        return 'mobile';
    }

    function resolveApplication(dashboard) {
        return dashboard.closest('#ada-generic-application');
    }

    function resolveAlarmBaseline(dashboard) {
        const application = resolveApplication(dashboard);
        return application ? application.querySelector(BASELINE_SELECTOR) : null;
    }

    function resolveOverviewControls(dashboard) {
        const application = resolveApplication(dashboard);
        return application ? application.querySelector(OVERVIEW_CONTROLS_SELECTOR) : null;
    }

    function mountOverviewControls(dashboard) {
        const baseline = resolveAlarmBaseline(dashboard);
        const controls = resolveOverviewControls(dashboard);
        if (baseline && controls && controls.parentElement !== baseline) {
            baseline.appendChild(controls);
        }
        return controls;
    }

    function rememberAlarmBaselinePointPosition(point) {
        if (point.dataset.adaIoOriginalPointX !== undefined) {
            return;
        }
        point.dataset.adaIoOriginalPointX = point.style.getPropertyValue(
            '--ada-alarm-baseline-point-x'
        );
    }

    function restoreAlarmBaseline(dashboard) {
        const baseline = resolveAlarmBaseline(dashboard);
        if (!baseline) {
            return;
        }
        baseline.querySelectorAll(BASELINE_POINT_SELECTOR).forEach((point) => {
            rememberAlarmBaselinePointPosition(point);
            point.hidden = false;
            point.style.setProperty(
                '--ada-alarm-baseline-point-x',
                point.dataset.adaIoOriginalPointX
            );
        });
        delete baseline.dataset.adaIoScope;
    }

    function focusAlarmBaseline(dashboard, scope) {
        const baseline = resolveAlarmBaseline(dashboard);
        if (!baseline) {
            return;
        }

        const points = Array.from(baseline.querySelectorAll(BASELINE_POINT_SELECTOR));
        points.forEach(rememberAlarmBaselinePointPosition);

        const visiblePoints = points.filter((point) => point.dataset.adaScope === scope);
        if (!visiblePoints.length) {
            restoreAlarmBaseline(dashboard);
            return;
        }

        points.forEach((point) => {
            point.hidden = point.dataset.adaScope !== scope;
        });
        visiblePoints.forEach((point, index) => {
            const positionPercent = ((index + 0.5) / visiblePoints.length) * 100;
            point.style.setProperty(
                '--ada-alarm-baseline-point-x',
                `${positionPercent.toFixed(6)}%`
            );
        });
        baseline.dataset.adaIoScope = scope;
    }

    function synchronizeAlarmBaseline(dashboard, mode, presentation) {
        const focused = presentation === 'mine' || presentation === 'plant';
        if ((mode === 'tablet' || mode === 'desktop') && focused) {
            focusAlarmBaseline(dashboard, presentation);
            return;
        }
        restoreAlarmBaseline(dashboard);
    }

    function synchronizeOverviewControls(dashboard, mode, presentation) {
        const controls = mountOverviewControls(dashboard);
        if (!controls) {
            return;
        }
        controls.dataset.adaIoViewport = mode;
        controls.dataset.adaIoPresentation = presentation;
    }

    function applyPresentation(dashboard, presentation) {
        if (VALID_PRESENTATIONS.has(presentation)) {
            dashboard.dataset.adaIoPresentation = presentation;
        }
    }

    function synchronizeDashboard(dashboard) {
        const previousMode = dashboard.dataset.adaIoViewport || '';
        const mode = resolveViewportMode(window.innerWidth);
        let presentation = dashboard.dataset.adaIoPresentation || 'overview';

        dashboard.dataset.adaIoViewport = mode;

        if (mode === 'mobile' || mode === 'videowall') {
            presentation = 'overview';
        } else if (mode === 'desktop') {
            if (previousMode && previousMode !== 'desktop') {
                presentation = 'overview';
            }
        } else if (
            previousMode !== 'tablet'
            || presentation === 'overview'
            || !VALID_PRESENTATIONS.has(presentation)
        ) {
            presentation = 'mine';
        }

        applyPresentation(dashboard, presentation);
        synchronizeAlarmBaseline(dashboard, mode, presentation);
        synchronizeOverviewControls(dashboard, mode, presentation);
    }

    function synchronizeAllDashboards() {
        document.querySelectorAll(DASHBOARD_SELECTOR).forEach(synchronizeDashboard);
    }

    function scheduleSynchronization() {
        if (resizeFrame !== null) {
            return;
        }
        resizeFrame = window.requestAnimationFrame(() => {
            resizeFrame = null;
            synchronizeAllDashboards();
        });
    }

    function resolveDashboardFromTrigger(trigger) {
        const directDashboard = trigger.closest(DASHBOARD_SELECTOR);
        if (directDashboard) {
            return directDashboard;
        }
        const application = trigger.closest('#ada-generic-application');
        return application ? application.querySelector(DASHBOARD_SELECTOR) : null;
    }

    function handleClick(event) {
        const trigger = event.target.closest(TARGET_SELECTOR);
        if (!trigger) {
            return;
        }

        const dashboard = resolveDashboardFromTrigger(trigger);
        if (!dashboard) {
            return;
        }

        const mode = resolveViewportMode(window.innerWidth);
        const presentation = trigger.dataset.adaIoPresentationTarget || '';
        if (!VALID_PRESENTATIONS.has(presentation) || mode === 'mobile' || mode === 'videowall') {
            return;
        }
        if (mode === 'tablet' && presentation === 'overview') {
            return;
        }

        applyPresentation(dashboard, presentation);
        synchronizeAlarmBaseline(dashboard, mode, presentation);
        synchronizeOverviewControls(dashboard, mode, presentation);
    }

    document.addEventListener('click', handleClick);
    document.addEventListener('DOMContentLoaded', scheduleSynchronization);
    window.addEventListener('load', scheduleSynchronization);
    window.addEventListener('resize', scheduleSynchronization);

    new MutationObserver(scheduleSynchronization).observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
})();
