(() => {
    'use strict';

    const overlay = document.getElementById('ada-io-startup-loader');
    if (!overlay || location.pathname !== '/' || overlay.classList.contains('ada-io-startup-loader--exit')) {
        return;
    }

    let scheduled = false;
    const observer = new MutationObserver(() => scheduleCheck());

    // Verifica la respuesta de alarmas, el indicador global y la primera salida de cada sector.
    // Los contenedores del body existen desde el layout, pero se llenan tras los callbacks.
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

    // Cuando terminó o venció el límite, no seguimos observando mutaciones de Dash.
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

    // Las actualizaciones de children y del atributo de alarmas activan otra comprobación.
    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['data-ada-io-alarm-ready', 'class'],
    });
    scheduleCheck();
})();
