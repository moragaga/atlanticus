(() => {
    'use strict';

    // Este asset controla solo presentación; no conoce datos ni contratos de backend.
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

    // Los botones Mina/Planta se mueven al Alarm Baseline para no cubrir las cards.
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

    // En focus, solo los puntos del scope visible se redistribuyen sobre todo el baseline.
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

    // Repartir columnas de la vista activa sin ocultar alarmas de la otra área.
    function resolveZoomAlarmPlacements(cards, points, presentation) {
        const count = Math.max(1, points.length, cards.length);
        const occupied = new Set();
        const entries = cards.map((card, index) => {
            const slot = Number(card.dataset.adaAlarmSlot || card.dataset.adaAlarmGroupSlot);
            const pointIndex = points.findIndex((point) =>
                point.dataset.adaComponentKey === card.dataset.adaAlarmDisplayComponentKey);
            const local = card.dataset.adaAlarmDisplayScope === presentation && pointIndex >= 0;
            const preferred = local
                ? Math.min(count - 1, Math.floor((pointIndex + .5) * count / points.length))
                : presentation === 'mine' ? count - 1 : 0;
            return {card, local, preferred, slot: Number.isFinite(slot) ? slot : index + 1, index};
        });
        entries.sort((a, b) => Number(b.local) - Number(a.local)
            || a.slot - b.slot || a.index - b.index);
        entries.forEach((entry) => {
            const available = Array.from({length: count}, (_, index) => index)
                .filter((index) => !occupied.has(index));
            available.sort((a, b) => Math.abs(a - entry.preferred) - Math.abs(b - entry.preferred)
                || (presentation === 'mine' && !entry.local ? b - a : a - b));
            entry.column = available[0] + 1;
            occupied.add(available[0]);
        });
        return {count, entries};
    }

    // Esta adaptación pertenece a Operaciones Integradas, no al Live genérico.
    function synchronizeAlarmCardPositions(dashboard, mode, presentation) {
        const application = resolveApplication(dashboard);
        const board = application && application.querySelector('.ada-alarm-live-board');
        if (!board) {
            return;
        }
        const cards = [...board.children].filter((child) =>
            child.matches('.ada-alarm-live-card, .ada-alarm-live-group'));
        const baseline = resolveAlarmBaseline(dashboard);
        const points = baseline ? [...baseline.querySelectorAll(BASELINE_POINT_SELECTOR)]
            .filter((point) => !point.hidden && point.dataset.adaScope === presentation
                && point.dataset.adaAlarmBaselineRegion === 'main') : [];
        if ((mode !== 'desktop' && mode !== 'tablet')
            || (presentation !== 'mine' && presentation !== 'plant') || !points.length) {
            if (board.dataset.adaIoAlarmZoom !== undefined) {
                delete board.dataset.adaIoAlarmZoom;
                board.style.removeProperty('--ada-io-alarm-zoom-count');
            }
            cards.forEach((card) => {
                if (card.style.getPropertyValue('--ada-io-alarm-zoom-column')) {
                    card.style.removeProperty('--ada-io-alarm-zoom-column');
                }
            });
            return;
        }
        const plan = resolveZoomAlarmPlacements(cards, points, presentation);
        board.dataset.adaIoAlarmZoom = presentation;
        if (board.style.getPropertyValue('--ada-io-alarm-zoom-count') !== String(plan.count)) {
            board.style.setProperty('--ada-io-alarm-zoom-count', String(plan.count));
        }
        plan.entries.forEach(({card, column}) => {
            if (card.style.getPropertyValue('--ada-io-alarm-zoom-column') !== String(column)) {
                card.style.setProperty('--ada-io-alarm-zoom-column', String(column));
            }
        });
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

    // Cada breakpoint conserva una semántica de presentación explícita.
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
        synchronizeAlarmCardPositions(dashboard, mode, presentation);
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

    // Los controles pueden vivir dentro del baseline, por eso resolvemos el dashboard vía aplicación.
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
        synchronizeAlarmCardPositions(dashboard, mode, presentation);
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {resolveZoomAlarmPlacements};
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
