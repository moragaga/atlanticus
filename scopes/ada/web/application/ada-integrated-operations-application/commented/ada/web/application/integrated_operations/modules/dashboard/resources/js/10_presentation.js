(() => {
    'use strict';

    // El JS solo modifica estado de presentación; no conoce datos ni contratos de backend.
    const DASHBOARD_SELECTOR = '[data-ada-module="dashboard"]';
    const TARGET_SELECTOR = '[data-ada-io-presentation-target]';
    const VALID_PRESENTATIONS = new Set(['overview', 'mine', 'plant']);

    function handleClick(event) {
        // La delegación permite que Dash regenere el árbol sin volver a registrar listeners por botón.
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
        // CSS consume este atributo para cambiar el ancho y desplazamiento del layout.
        dashboard.dataset.adaIoPresentation = presentation;
    }

    document.addEventListener('click', handleClick);
})();
