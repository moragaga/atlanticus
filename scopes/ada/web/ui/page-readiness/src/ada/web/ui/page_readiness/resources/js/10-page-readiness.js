(() => {
    'use strict';

    const SCOPE_SELECTOR = '[data-ada-page-readiness="true"]';
    const SIGNAL_SELECTOR = '[data-ada-component-key][data-ada-render-ready]';
    const states = new WeakMap();

    const stateFor = (scope) => {
        let state = states.get(scope);
        if (!state) {
            state = { timer: null, committed: false, ready: false };
            states.set(scope, state);
        }
        return state;
    };

    const loaderFor = (scope) => scope.querySelector(':scope > .ada-page-readiness__loader');

    const setScopeState = (scope, value) => {
        scope.setAttribute('data-ada-page-readiness-state', value);
        scope.setAttribute('aria-busy', value === 'ready' ? 'false' : 'true');
    };

    const clearSettle = (state) => {
        if (state.timer !== null) {
            window.clearTimeout(state.timer);
            state.timer = null;
        }
    };

    const finish = (scope, state) => {
        clearSettle(state);
        state.committed = true;
        state.ready = true;
        setScopeState(scope, 'ready');
        const loader = loaderFor(scope);
        if (loader) {
            loader.hidden = true;
        }
    };

    const transitionMilliseconds = (node) => {
        if (!node || typeof window.getComputedStyle !== 'function') {
            return 0;
        }
        const style = window.getComputedStyle(node);
        const parseTime = (value) => {
            const normalized = String(value || '').trim();
            if (normalized.endsWith('ms')) {
                return Number.parseFloat(normalized) || 0;
            }
            if (normalized.endsWith('s')) {
                return (Number.parseFloat(normalized) || 0) * 1000;
            }
            return 0;
        };
        const durations = String(style.transitionDuration || '0s').split(',').map(parseTime);
        const delays = String(style.transitionDelay || '0s').split(',').map(parseTime);
        return Math.max(0, ...durations.map((duration, index) => duration + (delays[index] || delays[0] || 0)));
    };

    const beginFade = (scope, state) => {
        if (state.committed || state.ready) {
            return;
        }
        state.committed = true;
        clearSettle(state);
        const loader = loaderFor(scope);
        if (!loader) {
            finish(scope, state);
            return;
        }
        loader.hidden = false;
        setScopeState(scope, 'fading');
        const duration = transitionMilliseconds(loader);
        if (duration <= 0) {
            window.requestAnimationFrame(() => finish(scope, state));
            return;
        }
        let completed = false;
        const complete = () => {
            if (completed) {
                return;
            }
            completed = true;
            loader.removeEventListener('transitionend', onTransitionEnd);
            finish(scope, state);
        };
        const onTransitionEnd = (event) => {
            if (event.target === loader && event.propertyName === 'opacity') {
                complete();
            }
        };
        loader.addEventListener('transitionend', onTransitionEnd);
        window.setTimeout(complete, Math.ceil(duration) + 80);
    };

    const currentSignals = (scope) =>
        Array.from(scope.querySelectorAll(SIGNAL_SELECTOR)).filter(
            (signal) => signal.closest(SCOPE_SELECTOR) === scope,
        );

    const allReady = (signals) =>
        signals.length > 0 && signals.every((signal) => signal.getAttribute('data-ada-render-ready') === 'true');

    const settleMilliseconds = (scope) => {
        const value = Number.parseInt(scope.getAttribute('data-ada-page-readiness-settle-ms') || '0', 10);
        return Number.isFinite(value) && value >= 0 ? value : 0;
    };

    const evaluate = (scope) => {
        const state = stateFor(scope);
        if (state.ready || state.committed) {
            return;
        }
        if (scope.getAttribute('data-ada-page-readiness-enabled') !== 'true') {
            finish(scope, state);
            return;
        }
        const signals = currentSignals(scope);
        if (!allReady(signals)) {
            clearSettle(state);
            setScopeState(scope, 'loading');
            const loader = loaderFor(scope);
            if (loader) {
                loader.hidden = false;
            }
            return;
        }
        clearSettle(state);
        setScopeState(scope, 'settling');
        state.timer = window.setTimeout(() => {
            state.timer = null;
            if (allReady(currentSignals(scope))) {
                beginFade(scope, state);
            } else {
                evaluate(scope);
            }
        }, settleMilliseconds(scope));
    };

    const refresh = () => {
        document.querySelectorAll(SCOPE_SELECTOR).forEach(evaluate);
    };

    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: [
            'data-ada-render-ready',
            'data-ada-component-key',
            'data-ada-page-readiness-enabled',
        ],
    });

    refresh();
})();
