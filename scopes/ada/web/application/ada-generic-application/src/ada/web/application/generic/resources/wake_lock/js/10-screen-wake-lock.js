(() => {
    'use strict';

    const OPERATIONAL_PATH = '/';
    const LOCATION_CHANGE_EVENT = 'ada:wake-lock-location-change';
    const UNSUPPORTED_MESSAGE = '[ADA Wake Lock] Screen Wake Lock API is not supported by this browser';
    const REQUEST_ERROR_MESSAGE = '[ADA Wake Lock] Failed to acquire screen wake lock';
    const RELEASED_MESSAGE = '[ADA Wake Lock] Screen wake lock was released by the browser';

    let sentinel = null;
    let requestInFlight = null;
    let unsupportedReported = false;

    const isOperationalSurface = () => window.location.pathname === OPERATIONAL_PATH;
    const shouldHoldWakeLock = () => (
        isOperationalSurface()
        && document.visibilityState === 'visible'
    );

    const reportUnsupported = () => {
        if (unsupportedReported) {
            return;
        }
        unsupportedReported = true;
        console.warn(UNSUPPORTED_MESSAGE);
    };

    const releaseWakeLock = async () => {
        const current = sentinel;
        sentinel = null;
        if (!current || current.released) {
            return;
        }
        await current.release();
    };

    const requestWakeLock = async () => {
        if (!shouldHoldWakeLock() || sentinel || requestInFlight) {
            return;
        }
        if (!('wakeLock' in navigator)) {
            reportUnsupported();
            return;
        }

        requestInFlight = navigator.wakeLock.request('screen');
        try {
            const acquired = await requestInFlight;
            if (!shouldHoldWakeLock()) {
                await acquired.release();
                return;
            }
            sentinel = acquired;
            acquired.addEventListener('release', () => {
                if (sentinel === acquired) {
                    sentinel = null;
                }
                if (shouldHoldWakeLock()) {
                    console.warn(RELEASED_MESSAGE);
                }
            });
        } catch (error) {
            if (shouldHoldWakeLock()) {
                console.error(REQUEST_ERROR_MESSAGE, error);
            }
        } finally {
            requestInFlight = null;
        }
    };

    const synchronize = () => {
        if (shouldHoldWakeLock()) {
            void requestWakeLock();
            return;
        }
        void releaseWakeLock();
    };

    const instrumentHistory = () => {
        for (const methodName of ['pushState', 'replaceState']) {
            const original = window.history[methodName];
            if (typeof original !== 'function' || original.__adaWakeLockWrapped === true) {
                continue;
            }
            const wrapped = function (...args) {
                const result = original.apply(this, args);
                window.dispatchEvent(new Event(LOCATION_CHANGE_EVENT));
                return result;
            };
            Object.defineProperty(wrapped, '__adaWakeLockWrapped', { value: true });
            window.history[methodName] = wrapped;
        }
    };

    const start = () => {
        instrumentHistory();
        document.addEventListener('visibilitychange', synchronize);
        window.addEventListener('pageshow', synchronize);
        window.addEventListener('popstate', synchronize);
        window.addEventListener(LOCATION_CHANGE_EVENT, synchronize);
        synchronize();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
