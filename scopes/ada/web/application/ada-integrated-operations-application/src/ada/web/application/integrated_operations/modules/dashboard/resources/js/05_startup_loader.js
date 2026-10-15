(() => {
    'use strict';

    const overlay = document.getElementById('ada-io-startup-loader');
    if (!overlay || location.pathname !== '/' || overlay.classList.contains('ada-io-startup-loader--exit')) {
        return;
    }

    let scheduled = false;
    const observer = new MutationObserver(() => scheduleCheck());

    function isReady() {
        const dashboard = document.getElementById('ada-integrated-operations-dashboard');
        if (!dashboard || dashboard.dataset.adaIoAlarmReady !== 'true') {
            return false;
        }
        const application = dashboard.closest('#ada-generic-application');
        if (!application || !application.querySelector('[data-ada-io-global-indicators-runtime="true"]')) {
            return false;
        }
        const panels = dashboard.querySelectorAll('[data-ada-io-component-key]');
        if (panels.length !== 9) {
            return false;
        }
        return Array.from(panels).every((panel) => {
            const content = panel.querySelector('[id^="ada-integrated-operations-card-"][id$="-content"]');
            return content !== null && content.childNodes.length > 0;
        });
    }

    function check() {
        scheduled = false;
        if (overlay.classList.contains('ada-io-startup-loader--exit')) {
            observer.disconnect();
            return;
        }
        if (isReady()) {
            overlay.classList.add('ada-io-startup-loader--exit');
            overlay.setAttribute('aria-hidden', 'true');
            observer.disconnect();
        }
    }

    function scheduleCheck() {
        if (!scheduled) {
            scheduled = true;
            window.requestAnimationFrame(check);
        }
    }

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['data-ada-io-alarm-ready', 'class'],
    });
    scheduleCheck();
})();
