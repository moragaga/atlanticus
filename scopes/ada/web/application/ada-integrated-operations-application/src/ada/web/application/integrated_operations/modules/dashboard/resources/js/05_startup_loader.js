(() => {
    'use strict';

    const overlay = document.getElementById('ada-io-startup-loader');
    if (!overlay || location.pathname !== '/' || typeof window.adaIoFinishStartupLoader !== 'function') {
        return;
    }

    const dashboardId = 'ada-integrated-operations-dashboard';
    const globalId = 'ada-operational-header-global-indicators-slot';
    const alarmId = 'ada-alarm-live-board';
    const timeSelector = '[data-ada-time-status-runtime-host="true"]';
    const expectedAreas = 9;
    let scheduled = false;
    let application = null;
    let applicationParent = null;

    const discoveryObserver = new MutationObserver(scheduleCheck);
    const applicationObserver = new MutationObserver(scheduleCheck);
    const parentObserver = new MutationObserver(scheduleCheck);

    function stop() {
        discoveryObserver.disconnect();
        applicationObserver.disconnect();
        parentObserver.disconnect();
        application = null;
        applicationParent = null;
    }

    function track() {
        const current = document.getElementById('ada-generic-application');
        if (current === application) {
            return;
        }
        applicationObserver.disconnect();
        parentObserver.disconnect();
        application = current;
        applicationParent = current ? current.parentNode : null;
        if (!current) {
            if (document.body) {
                discoveryObserver.observe(document.body, {childList: true, subtree: true});
            }
            return;
        }
        discoveryObserver.disconnect();
        applicationObserver.observe(current, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-ready'],
        });
        if (applicationParent) {
            parentObserver.observe(applicationParent, {childList: true});
        }
    }

    function pending() {
        const dashboard = document.getElementById(dashboardId);
        if (!dashboard || !application || !application.contains(dashboard)) {
            return ['dashboard'];
        }
        if (application.getAttribute('data-ada-content-state-presentation') === 'authoring') {
            application.setAttribute('data-startup-bypass', 'true');
            return [];
        }
        application.setAttribute('data-startup-bypass', 'false');
        const areas = Array.from(dashboard.querySelectorAll('[data-ada-io-component-key]'));
        const result = areas.filter((area) => area.getAttribute('data-ready') !== 'true')
            .map((area) => area.getAttribute('data-ada-io-component-key'));
        if (areas.length !== expectedAreas) {
            result.unshift('areas:' + areas.length + '/' + expectedAreas);
        }
        const global = document.getElementById(globalId);
        if (!global || !application.contains(global) || global.getAttribute('data-ready') !== 'true') {
            result.push('global_indicators');
        }
        const alarm = document.getElementById(alarmId);
        if (!alarm || !application.contains(alarm) || alarm.getAttribute('data-ready') !== 'true') {
            result.push('alarms_render');
        }
        const time = application.querySelector(timeSelector);
        if (!time || !['true', 'degraded'].includes(time.getAttribute('data-ready'))) {
            result.push('time_status');
        }
        return result;
    }

    function check() {
        scheduled = false;
        if (!document.getElementById('ada-io-startup-loader')) {
            stop();
            return;
        }
        track();
        if (pending().length === 0) {
            window.requestAnimationFrame(() => {
                if (document.getElementById('ada-io-startup-loader')
                    && pending().length === 0) {
                    window.adaIoFinishStartupLoader('ready');
                }
            });
        }
    }

    function scheduleCheck() {
        if (!scheduled) {
            scheduled = true;
            window.requestAnimationFrame(check);
        }
    }

    window.adaIoStopStartupObservers = stop;
    window.adaIoStartupPending = () => {
        track();
        return pending();
    };
    if (document.body) {
        discoveryObserver.observe(document.body, {childList: true, subtree: true});
    } else {
        document.addEventListener('DOMContentLoaded', scheduleCheck, {once: true});
    }
    scheduleCheck();
})();
