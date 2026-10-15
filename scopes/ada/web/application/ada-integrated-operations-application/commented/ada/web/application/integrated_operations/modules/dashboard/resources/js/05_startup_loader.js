(() => {
    'use strict';

    const overlay = document.getElementById('ada-io-startup-loader');
    if (!overlay || location.pathname !== '/' || typeof window.adaIoFinishStartupLoader !== 'function') {
        return;
    }

    // Los nueve callbacks señalan explícitamente data-ready=true en sus áreas.
    const expectedAreas = 9;
    const dashboardId = 'ada-integrated-operations-dashboard';
    const globalSlotId = 'ada-operational-header-global-indicators-slot';
    const alarmBoardId = 'ada-alarm-live-board';
    let scheduled = false;
    let dashboardTarget = null;
    let globalTarget = null;
    let alarmTarget = null;
    let watchingDiscovery = false;

    // Solo usamos el observador global para descubrir los tres puntos de montaje.
    // Después observamos atributos concretos, sin recorrer cambios de clases del dashboard.
    const discoveryObserver = new MutationObserver(scheduleCheck);
    const dashboardObserver = new MutationObserver(scheduleCheck);
    const globalObserver = new MutationObserver(scheduleCheck);
    const alarmObserver = new MutationObserver(scheduleCheck);

    function stop() {
        discoveryObserver.disconnect();
        dashboardObserver.disconnect();
        globalObserver.disconnect();
        alarmObserver.disconnect();
    }

    function track() {
        const dashboard = document.getElementById(dashboardId);
        if (dashboard && dashboard !== dashboardTarget) {
            dashboardObserver.disconnect();
            dashboardObserver.observe(dashboard, {
                subtree: true,
                attributes: true,
                attributeFilter: ['data-ready'],
            });
            dashboardTarget = dashboard;
        }

        const globalSlot = document.getElementById(globalSlotId);
        if (globalSlot && globalSlot !== globalTarget) {
            globalObserver.disconnect();
            globalObserver.observe(globalSlot, {
                childList: true,
                attributes: true,
                attributeFilter: ['data-slot-empty'],
            });
            globalTarget = globalSlot;
        }

        const alarmBoard = document.getElementById(alarmBoardId);
        if (alarmBoard && alarmBoard !== alarmTarget) {
            alarmObserver.disconnect();
            alarmObserver.observe(alarmBoard, {
                attributes: true,
                attributeFilter: ['style'],
            });
            alarmTarget = alarmBoard;
        }

        if (dashboardTarget && globalTarget && alarmTarget && watchingDiscovery) {
            discoveryObserver.disconnect();
            watchingDiscovery = false;
        }
    }

    // La alarma se considera renderizada cuando el callback publica la capacidad,
    // incluso si el collector continúa en waiting y no existen alarmas visibles.
    function pending() {
        const dashboard = document.getElementById(dashboardId);
        if (!dashboard) {
            return ['dashboard'];
        }
        const areas = Array.from(dashboard.querySelectorAll('[data-ada-io-component-key]'));
        const missing = areas.filter((area) => area.getAttribute('data-ready') !== 'true')
            .map((area) => area.getAttribute('data-ada-io-component-key'));
        if (areas.length !== expectedAreas) {
            missing.unshift('areas:' + areas.length + '/' + expectedAreas);
        }
        const application = dashboard.closest('#ada-generic-application');
        if (!application || !application.querySelector('[data-ada-io-global-indicators-runtime="true"]')) {
            missing.push('global_indicators');
        }
        const board = document.getElementById(alarmBoardId);
        if (!board || !board.style.getPropertyValue('--ada-alarm-live-slot-count')) {
            missing.push('alarms_render');
        }
        return missing;
    }

    function check() {
        scheduled = false;
        if (!document.getElementById('ada-io-startup-loader')) {
            stop();
            return;
        }
        track();
        if (pending().length === 0) {
            window.adaIoFinishStartupLoader('ready');
        }
    }

    function scheduleCheck() {
        if (!scheduled) {
            scheduled = true;
            window.requestAnimationFrame(check);
        }
    }

    window.adaIoStopStartupObservers = stop;
    window.adaIoStartupPending = pending;
    if (document.body) {
        discoveryObserver.observe(document.body, { childList: true, subtree: true });
        watchingDiscovery = true;
    }
    scheduleCheck();
})();
