(() => {
    'use strict';

    const MARKER_ID = 'ada-session-auto-reload';
    const OPERATIONAL_PATH = '/';

    const start = () => {
        const marker = document.getElementById(MARKER_ID);
        if (!marker) {
            return;
        }

        const reloadAfterMs = Number.parseInt(marker.dataset.reloadAfterMs, 10);
        const checkEveryMs = Number.parseInt(marker.dataset.checkEveryMs, 10);
        if (
            !Number.isFinite(reloadAfterMs)
            || reloadAfterMs <= 0
            || !Number.isFinite(checkEveryMs)
            || checkEveryMs <= 0
            || checkEveryMs > reloadAfterMs
        ) {
            return;
        }

        const deadlineMs = Date.now() + reloadAfterMs;
        let reloadRequested = false;

        const deadlineExpired = () => Date.now() >= deadlineMs;
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
            const delayMs = remainingMs <= 0
                ? checkEveryMs
                : Math.min(checkEveryMs, Math.max(1, remainingMs));
            window.setTimeout(runCheck, delayMs);
        };

        const runCheck = () => {
            maybeReload();
            scheduleNextCheck();
        };

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
