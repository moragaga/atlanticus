(() => {
    'use strict';

    // Wake Lock pertenece a la experiencia operacional ADA y no debe mantenerse en Manager.
    const OPERATIONAL_PATH = '/';
    // Dash puede cambiar pathname mediante History API sin recargar el documento; este evento
    // permite reconciliar el lock inmediatamente también en ese tipo de navegación.
    const LOCATION_CHANGE_EVENT = 'ada:wake-lock-location-change';
    const UNSUPPORTED_MESSAGE = '[ADA Wake Lock] Screen Wake Lock API is not supported by this browser';
    const REQUEST_ERROR_MESSAGE = '[ADA Wake Lock] Failed to acquire screen wake lock';
    const RELEASED_MESSAGE = '[ADA Wake Lock] Screen wake lock was released by the browser';

    // Sentinel representa el lock actualmente concedido. requestInFlight evita solicitudes
    // concurrentes si varios eventos de lifecycle ocurren casi simultáneamente.
    let sentinel = null;
    let requestInFlight = null;
    let unsupportedReported = false;

    const isOperationalSurface = () => window.location.pathname === OPERATIONAL_PATH;
    const shouldHoldWakeLock = () => (
        isOperationalSurface()
        && document.visibilityState === 'visible'
    );

    // La ausencia de soporte es una degradación conocida, no un fallo funcional de ADA.
    // Se informa una sola vez para que pueda detectarse durante pruebas del dispositivo.
    const reportUnsupported = () => {
        if (unsupportedReported) {
            return;
        }
        unsupportedReported = true;
        console.warn(UNSUPPORTED_MESSAGE);
    };

    // Al abandonar la superficie operacional o quedar oculta la pestaña liberamos explícitamente
    // el lock si continúa vigente. El navegador también puede liberarlo por su cuenta.
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
            // La visibilidad o ruta puede cambiar mientras la Promise está pendiente. Si ocurrió,
            // soltamos inmediatamente el sentinel recién adquirido.
            if (!shouldHoldWakeLock()) {
                await acquired.release();
                return;
            }
            sentinel = acquired;
            acquired.addEventListener('release', () => {
                if (sentinel === acquired) {
                    sentinel = null;
                }
                // Si el sistema revoca el lock mientras la página sigue siendo operacional y visible,
                // se deja evidencia diagnóstica pero no se entra en un loop agresivo de reintentos.
                if (shouldHoldWakeLock()) {
                    console.warn(RELEASED_MESSAGE);
                }
            });
        } catch (error) {
            // Una API presente que rechaza la adquisición mientras la superficie aún requiere el lock
            // sí es una operación fallida. Si la pestaña/ruta cambió durante la Promise, el rechazo
            // corresponde al cambio de lifecycle y no se reporta como falso positivo.
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

    // pushState/replaceState no emiten popstate. Se envuelve únicamente History API para emitir
    // una señal local después de una navegación programática y poder liberar el lock al entrar a Manager.
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
        // visibilitychange es la señal principal para liberar y readquirir en tablets.
        document.addEventListener('visibilitychange', synchronize);
        // pageshow cubre restauraciones de página y popstate la navegación del historial.
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
