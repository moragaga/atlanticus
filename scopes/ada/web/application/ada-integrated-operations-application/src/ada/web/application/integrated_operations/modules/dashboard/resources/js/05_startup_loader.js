(() => {
    'use strict';

    if (location.pathname !== '/' || typeof window.adaIoFinishStartupLoader !== 'function') {
        return;
    }

    const expected = [
        'ada-operational-header-global-indicators-slot',
        'ada-alarm-live-board',
    ];
    const timeSelector = '[data-ada-time-status-runtime-host="true"]';
    let queued = false;
    let completed = false;

    function stop() {
        observer.disconnect();
    }

    function complete() {
        queued = false;
        if (completed || !document.getElementById('ada-io-startup-loader')) {
            stop();
            return;
        }
        const dashboard = document.getElementById('ada-integrated-operations-dashboard');
        const areas = dashboard ? dashboard.querySelectorAll('[data-ada-io-component-key]') : [];
        if (areas.length !== 9 || Array.from(areas).some(node => node.getAttribute('data-ready') !== 'true')) {
            return;
        }
        if (expected.some(id => {
            const node = document.getElementById(id);
            return !node || node.getAttribute('data-ready') !== 'true';
        })) {
            return;
        }
        const time = document.querySelector(timeSelector);
        if (!time || !['true', 'degraded'].includes(time.getAttribute('data-ready'))) {
            return;
        }
        completed = true;
        stop();
        window.requestAnimationFrame(() => {
            if (document.getElementById('ada-io-startup-loader')) {
                window.adaIoFinishStartupLoader?.('ready');
            }
        });
    }

    function schedule() {
        if (!queued && !completed) {
            queued = true;
            window.requestAnimationFrame(complete);
        }
    }

    const observer = new MutationObserver(schedule);
    window.adaIoStopStartupObservers = stop;
    if (document.body) {
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-ready'],
        });
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['data-ready'],
            });
            schedule();
        }, {once: true});
    }
    schedule();
})();
