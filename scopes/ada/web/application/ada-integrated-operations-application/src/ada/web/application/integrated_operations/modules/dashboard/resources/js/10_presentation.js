(() => {
    'use strict';

    const DASHBOARD_SELECTOR = '[data-ada-module="dashboard"]';
    const TARGET_SELECTOR = '[data-ada-io-presentation-target]';
    const VALID_PRESENTATIONS = new Set(['overview', 'mine', 'plant']);

    function handleClick(event) {
        const trigger = event.target.closest(TARGET_SELECTOR);
        if (!trigger) {
            return;
        }
        const dashboard = trigger.closest(DASHBOARD_SELECTOR);
        if (!dashboard) {
            return;
        }
        const presentation = trigger.dataset.adaIoPresentationTarget || '';
        if (!VALID_PRESENTATIONS.has(presentation)) {
            return;
        }
        dashboard.dataset.adaIoPresentation = presentation;
    }

    document.addEventListener('click', handleClick);
})();
