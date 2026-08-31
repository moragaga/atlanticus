(() => {
    'use strict';

    const CONFIG_ID = 'atlanticus-runtime-config';
    const NAMESPACE = 'atlanticus:user-activity:v1';
    const KEYS = {
        session: `${NAMESPACE}:session`,
        sequence: `${NAMESPACE}:sequence`,
        pathname: `${NAMESPACE}:pathname`
    };
    const state = {
        config: null,
        started: false,
        starting: false,
        heartbeat: null,
        listenersInstalled: false,
        historyInstalled: false,
        resizeTimer: null
    };

    const config = () => {
        const element = document.getElementById(CONFIG_ID);
        if (!element) {
            return null;
        }
        try {
            const runtime = JSON.parse(element.textContent || '{}');
            return runtime?.modules?.['user-activity'] || null;
        } catch (error) {
            console.warn('[WARN] Atlanticus user activity config is invalid', error);
            return null;
        }
    };

    const id = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const pathname = () => window.location.pathname || '/';

    const sessionId = () => {
        const existing = window.sessionStorage.getItem(KEYS.session);
        if (existing) {
            return existing;
        }
        const value = id();
        window.sessionStorage.setItem(KEYS.session, value);
        return value;
    };

    const nextSequence = () => {
        const previous = Number.parseInt(window.sessionStorage.getItem(KEYS.sequence) || '0', 10);
        const value = Number.isFinite(previous) ? previous + 1 : 1;
        window.sessionStorage.setItem(KEYS.sequence, String(value));
        return value;
    };

    const payload = (eventType, previousPathname = null) => ({
        event_id: id(),
        client_session_id: sessionId(),
        sequence: nextSequence(),
        event_type: eventType,
        pathname: pathname(),
        previous_pathname: previousPathname,
        visibility_state: document.visibilityState === 'hidden' ? 'hidden' : 'visible',
        viewport: { width: window.innerWidth || 0, height: window.innerHeight || 0 },
        screen: {
            width: window.screen?.width || 0,
            height: window.screen?.height || 0,
            pixel_ratio: window.devicePixelRatio || 1
        },
        client_timestamp_utc: new Date().toISOString()
    });

    const post = async (eventType, options = {}) => {
        if (!state.started && eventType !== 'register') {
            return false;
        }
        const body = JSON.stringify(payload(eventType, options.previousPathname || null));
        if (options.beacon === true && typeof navigator.sendBeacon === 'function') {
            if (navigator.sendBeacon(state.config.event_endpoint, new Blob([body], { type: 'application/json' }))) {
                window.sessionStorage.setItem(KEYS.pathname, pathname());
                return true;
            }
        }
        try {
            const response = await fetch(state.config.event_endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                keepalive: options.keepalive === true,
                headers: { 'Content-Type': 'application/json' },
                body
            });
            if (response.ok) {
                window.sessionStorage.setItem(KEYS.pathname, pathname());
            }
            return response.ok;
        } catch (error) {
            console.warn(`[WARN] Atlanticus user activity failed: ${eventType}`, error);
            return false;
        }
    };

    const stopHeartbeat = () => {
        if (state.heartbeat !== null) {
            window.clearInterval(state.heartbeat);
            state.heartbeat = null;
        }
    };

    const startHeartbeat = () => {
        if (state.heartbeat !== null || document.visibilityState !== 'visible') {
            return;
        }
        state.heartbeat = window.setInterval(() => {
            if (document.visibilityState === 'visible') {
                post('heartbeat').catch(() => undefined);
            }
        }, state.config.heartbeat_ms);
    };

    const routeChanged = (previous) => {
        if (state.started && previous !== pathname()) {
            post('route_changed', { previousPathname: previous }).catch(() => undefined);
        }
    };

    const installHistory = () => {
        if (state.historyInstalled) {
            return;
        }
        state.historyInstalled = true;
        ['pushState', 'replaceState'].forEach((method) => {
            const original = window.history[method];
            if (typeof original !== 'function') {
                return;
            }
            window.history[method] = function (...args) {
                const previous = pathname();
                const result = original.apply(this, args);
                window.queueMicrotask(() => routeChanged(previous));
                return result;
            };
        });
        const restored = () => routeChanged(window.sessionStorage.getItem(KEYS.pathname) || '/');
        window.addEventListener('popstate', restored);
        window.addEventListener('hashchange', restored);
    };

    const installListeners = () => {
        if (state.listenersInstalled) {
            return;
        }
        state.listenersInstalled = true;
        document.addEventListener('visibilitychange', () => {
            if (!state.started) {
                return;
            }
            if (document.visibilityState === 'hidden') {
                stopHeartbeat();
                post('hidden', { beacon: true, keepalive: true }).catch(() => undefined);
                return;
            }
            post('visible').catch(() => undefined);
            startHeartbeat();
        });
        window.addEventListener('pagehide', () => {
            stopHeartbeat();
            post('pagehide', { beacon: true, keepalive: true }).catch(() => undefined);
        });
        window.addEventListener('resize', () => {
            if (state.resizeTimer !== null) {
                window.clearTimeout(state.resizeTimer);
            }
            state.resizeTimer = window.setTimeout(() => {
                state.resizeTimer = null;
                if (state.started && document.visibilityState === 'visible') {
                    post('heartbeat').catch(() => undefined);
                }
            }, 500);
        });
        installHistory();
    };

    const start = async () => {
        if (state.started || state.starting) {
            return;
        }
        state.config = config();
        if (!state.config?.enabled) {
            return;
        }
        state.starting = true;
        try {
            const response = await fetch(state.config.bootstrap_endpoint, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { Accept: 'application/json' }
            });
            if (!response.ok) {
                return;
            }
            const bootstrap = await response.json();
            if (bootstrap?.enabled !== true || bootstrap?.track !== true) {
                return;
            }
            installListeners();
            const registered = await post('register');
            if (!registered) {
                return;
            }
            state.started = true;
            startHeartbeat();
        } catch (error) {
            console.warn('[WARN] Atlanticus user activity could not start', error);
        } finally {
            state.starting = false;
        }
    };

    window.AtlanticusUserActivity = {
        start,
        heartbeat: () => post('heartbeat'),
        clear: () => {
            stopHeartbeat();
            Object.values(KEYS).forEach((key) => window.sessionStorage.removeItem(key));
            state.started = false;
            state.starting = false;
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => start().catch(() => undefined), { once: true });
    } else {
        start().catch(() => undefined);
    }
})();
