(() => {
    'use strict';

    const SURFACE = '.ada-alarm-live-surface';
    const BOARD = '.ada-alarm-live-board';
    const CARD = '.ada-alarm-live-card';
    const POINT = '.ada-alarm-baseline-surface__point';
    const ROUTES = '.ada-alarm-live-routes';
    const COMPONENT = '.ada-card-display[data-ada-subcomponent-key]';
    const NS = 'http://www.w3.org/2000/svg';
    const PREVIEW = Object.freeze({
        revealMs: 4000,
        holdMs: 20000,
        fadeMs: 3000,
        betweenMs: 250,
        cyclePauseMs: 1500,
        maxCycleSize: 6,
    });
    const controllers = new WeakMap();
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

    function nextPreviewKey(candidates, completed) {
        return candidates.find((key) => !completed.has(key)) || null;
    }

    function previewPlan(candidates, completed) {
        if (!candidates.length) {
            return {mode: 'idle', key: null};
        }
        if (candidates.length === 1) {
            return {mode: 'steady', key: candidates[0]};
        }
        const key = nextPreviewKey(candidates, completed);
        return key === null
            ? {mode: 'pause', key: null}
            : {mode: 'cycle', key};
    }

    function toggleSelection(current, clicked, available) {
        if (!available.includes(clicked)) {
            return current;
        }
        return current === clicked ? null : clicked;
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

    function candidateKeys(cards, paths, integrated) {
        const routed = new Set(paths.map((path) => path.dataset.adaAlarmOccurrenceId));
        const activeCards = cards.filter((card) =>
            visible(card)
            && card.dataset.adaAlarmGrouped !== 'true'
            && routed.has(card.dataset.adaAlarmOccurrenceId)
        );
        if (integrated) {
            activeCards.sort((a, b) =>
                a.getBoundingClientRect().left - b.getBoundingClientRect().left
            );
        }
        return activeCards.slice(0, PREVIEW.maxCycleSize)
            .map((card) => card.dataset.adaAlarmOccurrenceId);
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
        const svg = document.createElementNS(NS, 'svg');
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
                const path = document.createElementNS(NS, 'path');
                path.setAttribute('d', routePath(x, y, px, py));
                path.setAttribute('class', `ada-alarm-live-route ada-alarm-live-route--${color.toLowerCase()}`);
                path.setAttribute('data-ada-alarm-occurrence-id', card.dataset.adaAlarmOccurrenceId);
                path.setAttribute('data-ada-alarm-target-component', point.dataset.adaComponentKey);
                svg.appendChild(path);
                const length = path.getTotalLength();
                path.style.setProperty('--ada-alarm-live-route-length', `${length}px`);
                path.style.strokeDasharray = `${length} ${length}`;
            });
        });
        const controller = controllers.get(surface);
        const signature = [
            width, height,
            ...Array.from(svg.children).map((path) => [
                path.dataset.adaAlarmOccurrenceId,
                path.dataset.adaAlarmTargetComponent,
                path.getAttribute('class'),
                path.getAttribute('d'),
            ].join('|')),
        ].join('||');
        if (!controller || controller.geometrySignature !== signature) {
            overlay.replaceChildren(svg);
        }
        updateAffections(surface, cards);
        if (controller) {
            controller.geometrySignature = signature;
            controller.cards = cards;
            controller.points = points;
            controller.paths = Array.from(overlay.querySelectorAll('.ada-alarm-live-route'));
            const baseline = surface.querySelector('.ada-alarm-baseline-surface');
            controller.candidates = candidateKeys(
                cards, controller.paths,
                Boolean(baseline && baseline.dataset.adaAlarmBaseline === 'integrated_operations'),
            );
            reconcile(controller);
        }
    }

    function paint(controller) {
        const selected = controller.selected;
        const active = selected || controller.active;
        const phase = selected ? 'selected' : controller.phase;
        controller.surface.dataset.adaAlarmHasSelection = selected ? 'true' : 'false';
        controller.cards.forEach((card) => {
            const key = card.dataset.adaAlarmOccurrenceId;
            const isSelected = key === selected;
            const isPreviewing = key === active && !selected;
            card.dataset.adaAlarmSelected = String(isSelected);
            card.dataset.adaAlarmPreviewing = String(isPreviewing);
            if (card.dataset.adaAlarmGrouped !== 'true') {
                card.setAttribute('aria-pressed', String(isSelected));
            }
        });
        controller.paths.forEach((path) => {
            const focus = path.dataset.adaAlarmOccurrenceId === active;
            path.dataset.adaAlarmFocus = focus ? phase : 'idle';
            path.dataset.adaAlarmMuted = String(Boolean(selected) && !focus);
        });
        controller.points.forEach((point) => {
            const matching = controller.paths.filter((path) =>
                path.dataset.adaAlarmOccurrenceId === active
                && path.dataset.adaAlarmTargetComponent === point.dataset.adaComponentKey
            );
            const color = matching.some((path) => path.classList.contains('ada-alarm-live-route--red'))
                ? 'red' : matching.length ? 'yellow' : null;
            if (color) {
                point.dataset.adaAlarmLiveFocus = color;
            } else {
                delete point.dataset.adaAlarmLiveFocus;
            }
        });
    }

    function stopTimer(controller) {
        if (controller.timer !== null) {
            window.clearTimeout(controller.timer);
            controller.timer = null;
        }
        controller.generation += 1;
    }

    function scheduleTimer(controller, milliseconds, callback) {
        stopTimer(controller);
        const generation = controller.generation;
        controller.timer = window.setTimeout(() => {
            if (generation !== controller.generation || !controller.surface.isConnected) {
                return;
            }
            controller.timer = null;
            callback();
        }, milliseconds);
    }

    function advance(controller) {
        if (controller.selected) {
            return;
        }
        const plan = previewPlan(controller.candidates, controller.completed);
        if (plan.mode === 'idle') {
            controller.active = null;
            controller.phase = null;
            paint(controller);
            return;
        }
        if (plan.mode === 'steady') {
            controller.active = plan.key;
            controller.phase = 'steady';
            paint(controller);
            return;
        }
        if (plan.mode === 'pause') {
            controller.completed.clear();
            controller.active = null;
            controller.phase = null;
            paint(controller);
            scheduleTimer(controller, PREVIEW.cyclePauseMs, () => advance(controller));
            return;
        }
        controller.active = plan.key;
        controller.phase = 'reveal';
        paint(controller);
        scheduleTimer(controller, PREVIEW.revealMs, () => {
            controller.phase = 'hold';
            paint(controller);
            scheduleTimer(controller, PREVIEW.holdMs, () => {
                controller.phase = 'fade';
                paint(controller);
                scheduleTimer(controller, PREVIEW.fadeMs, () => {
                    controller.completed.add(plan.key);
                    controller.active = null;
                    controller.phase = null;
                    paint(controller);
                    scheduleTimer(controller, PREVIEW.betweenMs, () => advance(controller));
                });
            });
        });
    }

    function motionReduced() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function reconcile(controller) {
        const available = controller.cards
            .filter((card) => card.dataset.adaAlarmGrouped !== 'true')
            .map((card) => card.dataset.adaAlarmOccurrenceId);
        if (controller.selected && !available.includes(controller.selected)) {
            controller.selected = null;
            stopTimer(controller);
            controller.active = null;
            controller.completed.clear();
        }
        if (controller.selected || motionReduced()) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = null;
            paint(controller);
            return;
        }
        const availableCandidates = new Set(controller.candidates);
        for (const key of controller.completed) {
            if (!availableCandidates.has(key)) {
                controller.completed.delete(key);
            }
        }
        if (controller.active && !availableCandidates.has(controller.active)) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = null;
        }
        if (controller.candidates.length === 0) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = null;
            paint(controller);
            return;
        }
        if (controller.candidates.length === 1 && controller.phase !== 'steady') {
            stopTimer(controller);
            controller.completed.clear();
            controller.active = controller.candidates[0];
            controller.phase = 'steady';
        } else if (controller.candidates.length > 1 && controller.phase === 'steady') {
            stopTimer(controller);
            controller.active = null;
            controller.phase = null;
        }
        paint(controller);
        if (!controller.active && controller.timer === null) {
            advance(controller);
        }
    }

    function select(controller, occurrenceId) {
        const available = controller.cards
            .filter((card) => card.dataset.adaAlarmGrouped !== 'true')
            .map((card) => card.dataset.adaAlarmOccurrenceId);
        const next = toggleSelection(controller.selected, occurrenceId, available);
        if (next === controller.selected) {
            return;
        }
        stopTimer(controller);
        controller.selected = next;
        controller.active = null;
        controller.phase = null;
        controller.completed.clear();
        reconcile(controller);
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

    function attach(surface) {
        if (controllers.has(surface)) {
            return;
        }
        const board = surface.querySelector(BOARD);
        if (!board) {
            return;
        }
        const controller = {
            surface, cards: [], points: [], paths: [], candidates: [],
            selected: null, active: null, phase: null, completed: new Set(),
            timer: null, generation: 0,
        };
        controllers.set(surface, controller);
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
        schedule(surface);
    }

    function reconcileSurfaces() {
        document.querySelectorAll(SURFACE).forEach(attach);
    }

    function handleSelection(event) {
        if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        const card = event.target.closest && event.target.closest(CARD);
        if (!card || card.dataset.adaAlarmGrouped === 'true') {
            return;
        }
        const surface = card.closest(SURFACE);
        if (!surface) {
            return;
        }
        const controller = controllers.get(surface);
        if (!controller) {
            return;
        }
        if (event.type === 'keydown') {
            event.preventDefault();
        }
        select(controller, card.dataset.adaAlarmOccurrenceId);
    }

    if (typeof document !== 'undefined') {
        document.addEventListener('click', handleSelection);
        document.addEventListener('keydown', handleSelection);
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', reconcileSurfaces, {once: true});
        } else {
            reconcileSurfaces();
        }
        window.addEventListener('resize', () => {
            document.querySelectorAll(SURFACE).forEach(schedule);
        });
        new MutationObserver((records) => {
            if (records.every((record) => record.target.closest
                && record.target.closest(ROUTES))) {
                return;
            }
            reconcileSurfaces();
            document.querySelectorAll(SURFACE).forEach(schedule);
        }).observe(document.documentElement, {
            childList: true,
            subtree: true,
        });
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {routePath, previewPlan, toggleSelection};
    }
})();
