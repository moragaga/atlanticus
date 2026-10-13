(() => {
    'use strict';

    const SURFACE = '.ada-alarm-live-surface';
    const BOARD = '.ada-alarm-live-board';
    const CARD = '.ada-alarm-live-card';
    const POINT = '.ada-alarm-baseline-surface__point';
    const ROUTES = '.ada-alarm-live-routes';
    const ROUTE = '.ada-alarm-live-route';
    const MARKER = '.ada-alarm-live-marker';
    const COMPONENT = '.ada-card-display[data-ada-subcomponent-key]';
    const GROUP = '.ada-alarm-live-group';
    const GROUP_ITEM = '[data-ada-alarm-group-item="true"]';
    const GROUP_NAV = '[data-ada-alarm-group-navigation]';
    const NS = 'http://www.w3.org/2000/svg';
    const PREVIEW = Object.freeze({
        revealMs: 4000,
        holdMs: 20000,
        fadeMs: 3000,
        betweenMs: 250,
        cyclePauseMs: 1500,
        maxCycleSize: 6,
    });
    const GROUP_ROTATION_MS = PREVIEW.revealMs + PREVIEW.holdMs + PREVIEW.fadeMs + PREVIEW.betweenMs;
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

    function routePath(fromX, fromY, toX, toY, junctionY) {
        const middleY = junctionY === undefined ? fromY + (toY - fromY) * .45 : junctionY;
        return `M ${fromX} ${fromY} V ${middleY} H ${toX} V ${toY}`;
    }

    function previewPlan(candidates, completed) {
        if (!candidates.length) {
            return {mode: 'idle', key: null};
        }
        if (candidates.length === 1) {
            return {mode: 'steady', key: candidates[0]};
        }
        const key = candidates.find((candidate) => !completed.has(candidate));
        return key === undefined
            ? {mode: 'pause', key: null}
            : {mode: 'cycle', key};
    }

    function toggleSelection(current, clicked, available) {
        if (!available.includes(clicked)) {
            return current;
        }
        return current === clicked ? null : clicked;
    }

    function groupItemKey(card) {
        return `${card.dataset.adaAlarmGroupArea}:${card.dataset.adaAlarmOccurrenceId}`;
    }

    function groupChoice(choices, preferred) {
        const position = choices.indexOf(preferred);
        return position < 0 ? 0 : position;
    }

    function nextGroupIndex(count, position, direction) {
        if (count < 2) {
            return 0;
        }
        return (position + (direction === 'previous' ? count - 1 : 1)) % count;
    }

    function planIntegratedPositions(entries, boardWidth) {
        if (!entries.length || !Number.isFinite(boardWidth) || boardWidth <= 0) {
            return null;
        }
        const ordered = [...entries].sort((a, b) => a.x - b.x);
        const gap = 4;
        const maxWidth = boardWidth / 6 - gap;
        if (maxWidth <= 0) {
            return null;
        }
        const result = [];
        for (let index = 0; index < ordered.length; index += 1) {
            const entry = ordered[index];
            const left = index ? entry.x - ordered[index - 1].x : Number.POSITIVE_INFINITY;
            const right = index + 1 < ordered.length
                ? ordered[index + 1].x - entry.x : Number.POSITIVE_INFINITY;
            const width = Math.min(
                maxWidth, left - gap, right - gap,
                2 * entry.x - gap, 2 * (boardWidth - entry.x) - gap,
            );
            if (!Number.isFinite(entry.x) || width <= 0) {
                return null;
            }
            result.push({key: entry.key, x: entry.x, width});
        }
        return result;
    }

    function markerKind(isOrigin, targetCount) {
        if (!isOrigin) {
            return 'down';
        }
        return targetCount === 1 ? 'contract' : 'up';
    }

    function sortedPreviewCandidates(cards, routes, integrated) {
        const routed = new Set(routes.map((route) => route.dataset.adaAlarmOccurrenceId));
        const records = cards.filter((card) =>
            visible(card) && card.dataset.adaAlarmGrouped !== 'true'
            && routed.has(card.dataset.adaAlarmOccurrenceId)
        ).map((card, index) => ({
            key: card.dataset.adaAlarmOccurrenceId,
            tone: card.dataset.adaAlarmColor === 'RED' ? 0 :
                card.dataset.adaAlarmColor === 'YELLOW' ? 1 : 2,
            x: card.getBoundingClientRect().left,
            index,
        }));
        records.sort((a, b) => integrated
            ? a.x - b.x || a.tone - b.tone || a.index - b.index
            : a.tone - b.tone || a.index - b.index
        );
        return [...new Set(records.map((record) => record.key))].slice(0, PREVIEW.maxCycleSize);
    }

    function synchronizeGroups(controller, board) {
        const slots = new Set();
        board.querySelectorAll(GROUP).forEach((group) => {
            const slot = group.dataset.adaAlarmGroupSlot;
            const items = [...group.querySelectorAll(GROUP_ITEM)];
            if (!items.length) {
                return;
            }
            slots.add(slot);
            const choices = items.map(groupItemKey);
            const index = groupChoice(choices, controller.groupCurrent.get(slot));
            items.forEach((item, position) => {
                if (item.hidden !== (position !== index)) {
                    item.hidden = position !== index;
                }
            });
            controller.groupCurrent.set(slot, choices[index]);
            const counter = group.querySelector('.ada-alarm-live-group__counter');
            const label = `${index + 1}/${items.length}`;
            if (counter && counter.textContent !== label) {
                counter.textContent = label;
            }
        });
        [...controller.groupCurrent.keys()].forEach((slot) => {
            if (!slots.has(slot)) {
                controller.groupCurrent.delete(slot);
            }
        });
    }

    function moveGroup(controller, group, direction) {
        const items = [...group.querySelectorAll(GROUP_ITEM)];
        if (items.length < 2) {
            return false;
        }
        const slot = group.dataset.adaAlarmGroupSlot;
        const choices = items.map(groupItemKey);
        const current = groupChoice(choices, controller.groupCurrent.get(slot));
        controller.groupCurrent.set(slot, choices[nextGroupIndex(items.length, current, direction)]);
        schedule(controller.surface);
        return true;
    }

    function stopGroupTimer(controller) {
        if (controller.groupTimer !== null) {
            window.clearTimeout(controller.groupTimer);
            controller.groupTimer = null;
        }
    }

    function reconcileGroupTimer(controller) {
        const group = controller.surface.querySelector(GROUP);
        if (!group || !visible(group) || controller.selected || motionReduced()
            || group.querySelectorAll(GROUP_ITEM).length < 2) {
            stopGroupTimer(controller);
            return;
        }
        if (controller.groupTimer !== null) {
            return;
        }
        controller.groupTimer = window.setTimeout(() => {
            controller.groupTimer = null;
            if (controller.surface.isConnected && group.isConnected && !controller.selected) {
                moveGroup(controller, group, 'next');
            }
        }, GROUP_ROTATION_MS);
    }

    function integratedPosition(board, cards, points, integrated) {
        const direct = cards.filter((card) => card.parentElement === board && visible(card));
        const origin = board.getBoundingClientRect();
        const entries = direct.map((card) => {
            const key = card.dataset.adaAlarmDisplayComponentKey;
            const scope = card.dataset.adaAlarmDisplayScope;
            const point = points.find((candidate) =>
                candidate.dataset.adaComponentKey === key && candidate.dataset.adaScope === scope
            );
            return key && point ? {
                key: card.dataset.adaAlarmOccurrenceId,
                x: center(point.getBoundingClientRect(), origin),
            } : null;
        });
        const plan = integrated && entries.length && entries.every(Boolean)
            ? planIntegratedPositions(entries, origin.width) : null;
        if (!plan || plan.length !== direct.length) {
            delete board.dataset.adaAlarmLayout;
            cards.forEach((card) => {
                if (card.dataset.adaAlarmPositioned === 'true') {
                    delete card.dataset.adaAlarmPositioned;
                    card.style.removeProperty('--ada-alarm-live-display-x');
                    card.style.removeProperty('--ada-alarm-live-display-width');
                }
            });
            return;
        }
        plan.forEach((placement) => {
            const card = direct.find((item) => item.dataset.adaAlarmOccurrenceId === placement.key);
            const x = `${placement.x}px`;
            const width = `${placement.width}px`;
            if (card.style.getPropertyValue('--ada-alarm-live-display-x') !== x) {
                card.style.setProperty('--ada-alarm-live-display-x', x);
            }
            if (card.style.getPropertyValue('--ada-alarm-live-display-width') !== width) {
                card.style.setProperty('--ada-alarm-live-display-width', width);
            }
            card.dataset.adaAlarmPositioned = 'true';
        });
        board.dataset.adaAlarmLayout = 'integrated';
    }

    function addMarker(point, key, tone, kind) {
        const marker = document.createElement('span');
        marker.className = `ada-alarm-live-marker ada-alarm-live-marker--${tone.toLowerCase()}`
            + (kind === 'contract' ? ' ada-alarm-live-marker--contract' : '');
        marker.dataset.adaAlarmOccurrenceId = key;
        marker.dataset.adaAlarmFocus = 'idle';
        marker.setAttribute('aria-hidden', 'true');
        const arrows = kind === 'contract' ? ['up', 'down'] : [kind];
        arrows.forEach((direction) => {
            const arrow = document.createElement('span');
            arrow.className = `ada-alarm-live-marker__chevron ada-alarm-live-marker__chevron--${direction}`;
            marker.appendChild(arrow);
        });
        point.appendChild(marker);
        return marker;
    }

    function buildGeometry(controller, board, cards, points, integrated) {
        const surface = controller.surface;
        const overlay = surface.querySelector(ROUTES);
        const origin = surface.getBoundingClientRect();
        const boardRect = board.getBoundingClientRect();
        const width = Math.max(1, origin.width);
        const height = Math.max(1, origin.height);
        const definitions = [];
        const visibleCards = cards.filter(visible);
        visibleCards.forEach((card) => {
            if (card.dataset.adaAlarmGrouped === 'true') {
                return;
            }
            const targetKeys = keys(card.dataset.adaAlarmTargetComponents);
            const occurrence = card.dataset.adaAlarmOccurrenceId;
            const tone = card.dataset.adaAlarmColor;
            if (!targetKeys.size || (tone !== 'RED' && tone !== 'YELLOW')) {
                return;
            }
            const fromX = center(card.getBoundingClientRect(), origin);
            const fromY = boardRect.bottom - origin.top;
            const originComponent = card.dataset.adaAlarmDisplayComponentKey;
            const originScope = card.dataset.adaAlarmDisplayScope;
            const targets = points.filter((point) => targetKeys.has(point.dataset.adaComponentKey));
            targets.forEach((point) => {
                const rect = point.getBoundingClientRect();
                const toX = center(rect, origin);
                const toY = rect.top - origin.top + rect.height / 2;
                if (toY <= fromY) {
                    return;
                }
                const junctionY = fromY + (toY - fromY) * .28;
                const d = routePath(fromX, fromY, toX, toY, junctionY);
                const length = Math.abs(fromY - junctionY) + Math.abs(fromX - toX)
                    + Math.abs(junctionY - toY);
                const isOrigin = originComponent === point.dataset.adaComponentKey
                    && originScope === point.dataset.adaScope;
                definitions.push({
                    occurrence, tone, point,
                    kind: markerKind(isOrigin, targets.length), d, length,
                });
            });
        });
        const signature = [width, height,
            ...definitions.map((item) => `${item.occurrence}|${item.tone}|${item.kind}|${item.d}`),
        ].join('||');
        const sameAnchors = controller.anchorNodes.length === points.length
            && points.every((point, index) => controller.anchorNodes[index] === point);
        if (signature !== controller.geometrySignature || !sameAnchors
            || !overlay.querySelector('svg')
            || surface.querySelectorAll(MARKER).length !== definitions.length) {
            const svg = document.createElementNS(NS, 'svg');
            svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
            svg.setAttribute('preserveAspectRatio', 'none');
            svg.setAttribute('aria-hidden', 'true');
            const markerDefinitions = [];
            definitions.forEach(({occurrence, tone, point, kind, d, length}) => {
                const path = document.createElementNS(NS, 'path');
                path.setAttribute('d', d);
                path.setAttribute('class', `ada-alarm-live-route ada-alarm-live-route--${tone.toLowerCase()}`);
                path.dataset.adaAlarmOccurrenceId = occurrence;
                path.dataset.adaAlarmFocus = 'idle';
                svg.appendChild(path);
                path.style.setProperty('--ada-alarm-live-route-length', `${length}px`);
                markerDefinitions.push({occurrence, tone, point, kind});
            });
            points.forEach((point) => point.querySelectorAll(MARKER).forEach((marker) => marker.remove()));
            markerDefinitions.forEach(({occurrence, tone, point, kind}) => {
                addMarker(point, occurrence, tone, kind);
            });
            overlay.replaceChildren(svg);
            controller.geometrySignature = signature;
            controller.anchorNodes = [...points];
        }
        controller.cards = cards;
        controller.points = points;
        controller.paths = [...overlay.querySelectorAll(ROUTE)];
        controller.markers = [...surface.querySelectorAll(MARKER)];
        controller.candidates = sortedPreviewCandidates(cards, controller.paths, integrated);
    }

    function updateAffections(controller) {
        const application = controller.surface.closest('#ada-generic-application');
        if (!application) {
            return;
        }
        const palette = new Map();
        const focused = controller.selected || controller.active;
        const focusedKeys = new Set();
        controller.cards.filter(visible).forEach((card) => {
            const color = card.dataset.adaAlarmColor;
            if (color !== 'RED' && color !== 'YELLOW') {
                return;
            }
            const subcomponents = keys(card.dataset.adaAlarmTargetSubcomponents);
            subcomponents.forEach((key) => {
                if (!palette.has(key)) {
                    palette.set(key, new Set());
                }
                palette.get(key).add(color);
            });
            if (card.dataset.adaAlarmOccurrenceId === focused) {
                subcomponents.forEach((key) => focusedKeys.add(key));
            }
        });
        application.querySelectorAll(COMPONENT).forEach((component) => {
            const key = component.dataset.adaSubcomponentKey;
            const colors = palette.get(key);
            const value = !colors || !colors.size ? null
                : colors.size > 1 ? 'mixed' : colors.has('RED') ? 'red' : 'yellow';
            if (value) {
                component.dataset.adaAlarmAffection = value;
            } else {
                delete component.dataset.adaAlarmAffection;
            }
            if (focusedKeys.has(key)) {
                component.dataset.adaAlarmFocused = 'true';
            } else {
                delete component.dataset.adaAlarmFocused;
            }
        });
    }

    function paint(controller, restartReveal = false) {
        const focused = controller.selected || controller.active;
        const phase = controller.selected ? 'selected' : focused ? controller.phase : 'idle';
        controller.surface.dataset.adaAlarmHasSelection = controller.selected ? 'true' : 'false';
        controller.cards.forEach((card) => {
            const key = card.dataset.adaAlarmOccurrenceId;
            const selected = Boolean(controller.selected && controller.selected === key);
            const preview = !controller.selected && Boolean(controller.active && controller.active === key);
            card.dataset.adaAlarmSelected = String(selected);
            card.dataset.adaAlarmPreviewing = String(preview);
            if (card.dataset.adaAlarmGrouped !== 'true') {
                card.setAttribute('aria-pressed', String(selected));
            }
        });
        [...controller.paths, ...controller.markers].forEach((element) => {
            const focus = focused && element.dataset.adaAlarmOccurrenceId === focused;
            const next = focus ? phase : 'idle';
            if (restartReveal && next === 'reveal') {
                element.dataset.adaAlarmFocus = 'idle';
                void element.getBoundingClientRect();
            }
            if (element.dataset.adaAlarmFocus !== next) {
                element.dataset.adaAlarmFocus = next;
            }
        });
        updateAffections(controller);
    }

    function stopTimer(controller) {
        controller.generation += 1;
        if (controller.timer !== null) {
            window.clearTimeout(controller.timer);
            controller.timer = null;
        }
    }

    function timer(controller, ms, callback) {
        stopTimer(controller);
        const generation = controller.generation;
        controller.timer = window.setTimeout(() => {
            if (controller.generation !== generation || !controller.surface.isConnected) {
                return;
            }
            controller.timer = null;
            callback();
        }, ms);
    }

    function motionReduced() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function advance(controller) {
        if (controller.selected) {
            return;
        }
        const plan = previewPlan(controller.candidates, controller.completed);
        if (plan.mode === 'idle') {
            controller.active = null;
            controller.phase = 'idle';
            paint(controller);
            return;
        }
        if (plan.mode === 'steady' || motionReduced()) {
            controller.active = plan.mode === 'steady' ? plan.key : controller.candidates[0];
            controller.phase = 'steady';
            paint(controller);
            return;
        }
        if (plan.mode === 'pause') {
            controller.completed.clear();
            controller.active = null;
            controller.phase = 'idle';
            paint(controller);
            timer(controller, PREVIEW.cyclePauseMs, () => advance(controller));
            return;
        }
        controller.active = plan.key;
        controller.phase = 'reveal';
        paint(controller, true);
        timer(controller, PREVIEW.revealMs, () => {
            controller.phase = 'hold';
            paint(controller);
            timer(controller, PREVIEW.holdMs, () => {
                controller.phase = 'fade';
                paint(controller);
                timer(controller, PREVIEW.fadeMs, () => {
                    controller.completed.add(plan.key);
                    controller.active = null;
                    controller.phase = 'idle';
                    paint(controller);
                    timer(controller, PREVIEW.betweenMs, () => advance(controller));
                });
            });
        });
    }

    function reconcile(controller) {
        const available = controller.cards.filter((card) =>
            visible(card) && card.dataset.adaAlarmGrouped !== 'true'
        ).map((card) => card.dataset.adaAlarmOccurrenceId);
        if (controller.selected && !available.includes(controller.selected)) {
            controller.selected = null;
            stopTimer(controller);
            controller.active = null;
            controller.completed.clear();
        }
        if (controller.selected) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = 'idle';
            paint(controller);
            return;
        }
        const current = new Set(controller.candidates);
        [...controller.completed].forEach((key) => {
            if (!current.has(key)) {
                controller.completed.delete(key);
            }
        });
        if (controller.active && !current.has(controller.active)) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = 'idle';
        }
        if (!controller.candidates.length) {
            stopTimer(controller);
            controller.active = null;
            controller.phase = 'idle';
            paint(controller);
            return;
        }
        if (controller.candidates.length === 1 || motionReduced()) {
            stopTimer(controller);
            controller.completed.clear();
            controller.active = controller.candidates[0];
            controller.phase = 'steady';
            paint(controller);
            return;
        }
        if (controller.phase === 'steady') {
            stopTimer(controller);
            controller.active = null;
            controller.phase = 'idle';
        }
        paint(controller);
        if (!controller.active && controller.timer === null) {
            advance(controller);
        }
    }

    function select(controller, key) {
        const available = controller.cards.filter((card) =>
            visible(card) && card.dataset.adaAlarmGrouped !== 'true'
        ).map((card) => card.dataset.adaAlarmOccurrenceId);
        const next = toggleSelection(controller.selected, key, available);
        if (next === controller.selected) {
            return;
        }
        stopTimer(controller);
        controller.selected = next;
        controller.active = null;
        controller.phase = 'idle';
        controller.completed.clear();
        reconcile(controller);
        reconcileGroupTimer(controller);
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
        const controller = controllers.get(surface);
        if (!controller) {
            return;
        }
        synchronizeGroups(controller, board);
        const cards = [...board.querySelectorAll(CARD)];
        const points = [...surface.querySelectorAll(POINT)].filter(visible);
        const baseline = surface.querySelector('.ada-alarm-baseline-surface');
        const integrated = Boolean(baseline && baseline.dataset.adaAlarmBaseline === 'integrated_operations');
        integratedPosition(board, cards, points, integrated);
        buildGeometry(controller, board, cards, points, integrated);
        reconcile(controller);
        reconcileGroupTimer(controller);
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
        const controller = {
            surface, cards: [], points: [], paths: [], markers: [], candidates: [],
            selected: null, active: null, phase: 'idle', completed: new Set(),
            timer: null, generation: 0, geometrySignature: null, anchorNodes: [],
            groupCurrent: new Map(), groupTimer: null,
        };
        controllers.set(surface, controller);
        const board = surface.querySelector(BOARD);
        if (!board) {
            return;
        }
        new MutationObserver(() => schedule(surface)).observe(board, {
            childList: true, subtree: true,
        });
        new MutationObserver(() => schedule(surface)).observe(surface, {
            subtree: true, attributes: true,
            attributeFilter: ['style', 'hidden', 'data-ada-io-scope'],
        });
        if (typeof ResizeObserver !== 'undefined') {
            const resize = new ResizeObserver(() => schedule(surface));
            resize.observe(surface);
            resize.observe(board);
        }
        schedule(surface);
    }

    function reconcileSurfaces() {
        document.querySelectorAll(SURFACE).forEach(attach);
    }

    function handleSelection(event) {
        if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) {
            return;
        }
        const target = event.target;
        if (!target || !target.closest) {
            return;
        }
        const navigation = event.type === 'click' ? target.closest(GROUP_NAV) : null;
        if (navigation) {
            const group = navigation.closest(GROUP);
            const surface = group && group.closest(SURFACE);
            const controller = surface && controllers.get(surface);
            if (!controller) {
                return;
            }
            stopGroupTimer(controller);
            stopTimer(controller);
            controller.selected = null;
            controller.active = null;
            controller.phase = 'idle';
            controller.completed.clear();
            moveGroup(controller, group, navigation.dataset.adaAlarmGroupNavigation);
            return;
        }
        if (target.closest('button')) {
            return;
        }
        const card = target.closest(CARD);
        if (!card || card.hidden || card.dataset.adaAlarmGrouped === 'true') {
            return;
        }
        const controller = controllers.get(card.closest(SURFACE));
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
        window.addEventListener('resize', () => document.querySelectorAll(SURFACE).forEach(schedule));
        new MutationObserver((records) => {
            if (records.every((record) => record.target.closest && record.target.closest(ROUTES))) {
                return;
            }
            reconcileSurfaces();
            document.querySelectorAll(SURFACE).forEach(schedule);
        }).observe(document.documentElement, {childList: true, subtree: true});
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            routePath, previewPlan, toggleSelection, groupChoice, nextGroupIndex,
            planIntegratedPositions, markerKind, sortedPreviewCandidates,
        };
    }
})();
