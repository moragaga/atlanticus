(() => {
    if (!('serviceWorker' in navigator)) {
        return;
    }

    const runtimeElement = document.getElementById('atlanticus-runtime-config');

    if (!runtimeElement) {
        return;
    }

    let runtimeConfig;

    try {
        runtimeConfig = JSON.parse(runtimeElement.textContent || '{}');
    } catch {
        return;
    }

    const config = runtimeConfig.modules?.pwa;

    if (!config?.service_worker_url || !config?.scope) {
        return;
    }

    window.addEventListener('load', () => {
        navigator.serviceWorker
            .register(config.service_worker_url, { scope: config.scope })
            .catch(() => undefined);
    });
})();
