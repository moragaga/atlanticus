(() => {
    'use strict';

    // El marker estable publicado por ADA transporta únicamente los intervalos del workaround.
    const MARKER_ID = 'ada-session-auto-reload';
    // La política es explícita: sólo la raíz operacional puede forzar reload.
    const OPERATIONAL_PATH = '/';

    const start = () => {
        const marker = document.getElementById(MARKER_ID);
        if (!marker) {
            return;
        }

        const reloadAfterMs = Number.parseInt(marker.dataset.reloadAfterMs, 10);
        const checkEveryMs = Number.parseInt(marker.dataset.checkEveryMs, 10);
        // Un marker inválido desactiva el workaround sin impedir que ADA arranque.
        if (
            !Number.isFinite(reloadAfterMs)
            || reloadAfterMs <= 0
            || !Number.isFinite(checkEveryMs)
            || checkEveryMs <= 0
            || checkEveryMs > reloadAfterMs
        ) {
            return;
        }

        // El plazo nace al cargar la página; no se persiste entre navegaciones o sesiones.
        const deadlineMs = Date.now() + reloadAfterMs;
        let reloadRequested = false;

        const deadlineExpired = () => Date.now() >= deadlineMs;
        // Se consulta pathname en cada evaluación para respetar navegación client-side hacia o desde Manager.
        const isOperationalSurface = () => window.location.pathname === OPERATIONAL_PATH;

        const maybeReload = () => {
            if (
                reloadRequested
                || !deadlineExpired()
                || !isOperationalSurface()
                || document.visibilityState !== 'visible'
            ) {
                return false;
            }

            reloadRequested = true;
            window.location.reload();
            return true;
        };

        const scheduleNextCheck = () => {
            if (reloadRequested) {
                return;
            }
            const remainingMs = deadlineMs - Date.now();
            // Si venció estando hidden, se conserva la cadencia normal para evitar un loop de timers.
            const delayMs = remainingMs <= 0
                ? checkEveryMs
                : Math.min(checkEveryMs, Math.max(1, remainingMs));
            window.setTimeout(runCheck, delayMs);
        };

        const runCheck = () => {
            maybeReload();
            scheduleNextCheck();
        };

        // Volver a visible después del vencimiento ejecuta el reload sin esperar el siguiente chequeo.
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                maybeReload();
            }
        });

        scheduleNextCheck();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
