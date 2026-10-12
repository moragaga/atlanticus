(() => {
    'use strict';

    const SURFACE = '.ada-alarm-live-surface';
    const BOARD = '.ada-alarm-live-board';
    const CARD = '.ada-alarm-live-card';
    const POINT = '.ada-alarm-baseline-surface__point';
    const ROUTES = '.ada-alarm-live-routes';
    const COMPONENT = '.ada-card-display[data-ada-subcomponent-key]';
    const namespace = 'http://www.w3.org/2000/svg';
    const scheduled = new WeakSet();

    function keys(value) {
        return new Set((value || '').split(/\s+/).filter(Boolean));
    }

    function visible(element) {
        return !element.hidden && element.getClientRects().length > 0;
    }

    function center(rect, origin) {
        return rect.left - origin.left + rect.width / 2;
    }

    function routePath(fromX, fromY, toX, toY) {
        const middleY = fromY + (toY - fromY) * 0.45;
        return `M ${fromX} ${fromY} V ${middleY} H ${toX} V ${toY}`;
    }

    function updateAffections(surface, cards) {
        const application = surface.closest('#ada-generic-application');
        if (!application) {
            return;
        }
        const palette = new Map();
        cards.forEach((card) => {
            const color = card.dataset.adaAlarmColor;
            if (color !== 'RED' && color !== 'YELLOW') {
                return;
            }
            keys(card.dataset.adaAlarmTargetSubcomponents).forEach((key) => {
                if (!palette.has(key)) {
                    palette.set(key, new Set());
                }
                palette.get(key).add(color);
            });
        });
        application.querySelectorAll(COMPONENT).forEach((component) => {
            const colors = palette.get(component.dataset.adaSubcomponentKey);
            if (!colors || !colors.size) {
                delete component.dataset.adaAlarmAffection;
            } else {
                component.dataset.adaAlarmAffection = colors.size > 1
                    ? 'mixed' : colors.has('RED') ? 'red' : 'yellow';
            }
        });
    }

    function render(surface) {
        if (!surface.isConnected) {
            return;
        }
        const board = surface.querySelector(BOARD);
        const overlay = surface.querySelector(ROUTES);
        if (!board || !overlay) {
            return;
        }
        const cards = Array.from(board.querySelectorAll(CARD));
        const origin = surface.getBoundingClientRect();
        const width = Math.max(1, origin.width);
        const height = Math.max(1, origin.height);
        const svg = document.createElementNS(namespace, 'svg');
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('aria-hidden', 'true');
        const points = Array.from(surface.querySelectorAll(POINT)).filter(visible);
        cards.forEach((card) => {
            if (!visible(card) || card.dataset.adaAlarmGrouped === 'true') {
                return;
            }
            const targets = keys(card.dataset.adaAlarmTargetComponents);
            const color = card.dataset.adaAlarmColor;
            if (!targets.size || (color !== 'RED' && color !== 'YELLOW')) {
                return;
            }
            const rect = card.getBoundingClientRect();
            const x = center(rect, origin);
            const y = rect.bottom - origin.top;
            points.forEach((point) => {
                if (!targets.has(point.dataset.adaComponentKey)) {
                    return;
                }
                const targetRect = point.getBoundingClientRect();
                const px = center(targetRect, origin);
                const py = targetRect.top - origin.top + targetRect.height / 2;
                if (py <= y) {
                    return;
                }
                const path = document.createElementNS(namespace, 'path');
                path.setAttribute('d', routePath(x, y, px, py));
                path.setAttribute('class', `ada-alarm-live-route ada-alarm-live-route--${color.toLowerCase()}`);
                path.setAttribute('data-ada-alarm-occurrence-id', card.dataset.adaAlarmOccurrenceId);
                svg.appendChild(path);
            });
        });
        overlay.replaceChildren(svg);
        updateAffections(surface, cards);
    }

    function schedule(surface) {
        if (scheduled.has(surface)) {
            return;
        }
        scheduled.add(surface);
        window.requestAnimationFrame(() => {
            scheduled.delete(surface);
            render(surface);
        });
    }

    const observers = new WeakMap();

    function attach(surface) {
        if (observers.has(surface)) {
            return;
        }
        const board = surface.querySelector(BOARD);
        if (!board) {
            return;
        }
        const boardObserver = new MutationObserver(() => schedule(surface));
        boardObserver.observe(board, {childList: true, subtree: true});
        const pointObserver = new MutationObserver(() => schedule(surface));
        pointObserver.observe(surface, {
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'hidden', 'data-ada-io-scope'],
        });
        const resizeObserver = new ResizeObserver(() => schedule(surface));
        resizeObserver.observe(surface);
        resizeObserver.observe(board);
        observers.set(surface, {boardObserver, pointObserver, resizeObserver});
        schedule(surface);
    }

    function reconcile() {
        document.querySelectorAll(SURFACE).forEach(attach);
    }

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', reconcile, {once: true});
        } else {
            reconcile();
        }
        window.addEventListener('resize', () => {
            document.querySelectorAll(SURFACE).forEach(schedule);
        });
        new MutationObserver((records) => {
            if (records.every((record) => record.target.closest
                && record.target.closest(ROUTES))) {
                return;
            }
            reconcile();
            document.querySelectorAll(SURFACE).forEach(schedule);
        }).observe(document.documentElement, {
            childList: true,
            subtree: true,
        });
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {routePath};
    }
})();
