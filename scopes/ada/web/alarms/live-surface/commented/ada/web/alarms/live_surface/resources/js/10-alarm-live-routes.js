// Espejo pedagógico: solo gobierna visualización local, sin consultar el backend.
// El carousel recorre miembros previamente elegidos por operator_view.
// La selección detiene la rotación y reduce el riesgo de cambios bajo interacción.
(() => {
    'use strict';

    const SURFACE = '.ada-alarm-live-surface';
    const BOARD = '.ada-alarm-live-board';
    const CARD = '.ada-alarm-live-card';
    const POINT = '.ada-alarm-baseline-surface__point';
    const ROUTES = '.ada-alarm-live-routes';
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

    // Conserva la identidad (área y ocurrencia) cuando Dash reconstruye las cards.
    function synchronizeGroups(controller, board) {
        const slots = new Set();
        board.querySelectorAll(GROUP).forEach((group) => {
            const slot = group.dataset.adaAlarmGroupSlot;
            const items = Array.from(group.querySelectorAll(GROUP_ITEM));
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
        Array.from(controller.groupCurrent.keys()).forEach((slot) => {
            if (!slots.has(slot)) {
                controller.groupCurrent.delete(slot);
            }
        });
    }

    // Los controles alteran solo el índice visible; no cambian el orden del backend.
    function moveGroup(controller, group, direction) {
        const items = Array.from(group.querySelectorAll(GROUP_ITEM));
        if (items.length < 2) {
            return false;
        }
        const slot = group.dataset.adaAlarmGroupSlot;
        const keys = items.map(groupItemKey);
        const current = groupChoice(keys, controller.groupCurrent.get(slot));
        controller.groupCurrent.set(slot, keys[nextGroupIndex(items.length, current, direction)]);
        schedule(controller.surface);
        return true;
    }

    function stopGroupTimer(controller) {
        if (controller.groupTimer !== null) {
            window.clearTimeout(controller.groupTimer);
            controller.groupTimer = null;
        }
    }

    // Usa la duración total del preview y respeta reduced-motion y selección.
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
            if (controller.surface.isConnected && group.isConnected
                && !controller.selected && !motionReduced()) {
                moveGroup(controller, group, 'next');
            }
        }, GROUP_ROTATION_MS);
    }

    // Solo las alarmas visibles afectan el resaltado de subcomponentes.
    function updateAffections(surface, cards) {
        const application = surface.closest('#ada-generic-application');
        if (!application) {
            return;
        }
        const palette = new Map();
        cards.filter(visible).forEach((card) => {
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

    // Calcula anchos que no se pisan aunque dos Component tengan puntos cercanos.
    // El backend ya escogió las ocurrencias y sus slots: aquí solo ubicamos sus cards.
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

    // El anclaje debe coincidir con el Component y el área real de la baseline.
    // Si algún anclaje no existe, conserva el layout por slots y no inventa su geometría.
    function positionIntegratedCards(board, cards, points) {
        const direct = cards.filter((card) => card.parentElement === board && visible(card));
        const origin = board.getBoundingClientRect();
        const placements = direct.map((card) => {
            const key = card.dataset.adaAlarmDisplayComponentKey;
            const scope = card.dataset.adaAlarmDisplayScope;
            const point = points.find((candidate) =>
                candidate.dataset.adaComponentKey === key
                && candidate.dataset.adaScope === scope
            );
            if (!key || !point) {
                return null;
            }
            return {key: card.dataset.adaAlarmOccurrenceId,
                x: center(point.getBoundingClientRect(), origin)};
        });
        const plan = placements.every(Boolean)
            ? planIntegratedPositions(placements, origin.width) : null;
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
        if (controller) {
            synchronizeGroups(controller, board);
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
        const baseline = surface.querySelector('.ada-alarm-baseline-surface');
        if (baseline && baseline.dataset.adaAlarmBaseline === 'integrated_operations') {
            positionIntegratedCards(board, cards, points);
        }
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
            reconcileGroupTimer(controller);
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
            .filter((card) => visible(card) && card.dataset.adaAlarmGrouped !== 'true')
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
            .filter((card) => visible(card) && card.dataset.adaAlarmGrouped !== 'true')
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
        const board = surface.querySelector(BOARD);
        if (!board) {
            return;
        }
        const controller = {
            surface, cards: [], points: [], paths: [], candidates: [],
            selected: null, active: null, phase: null, completed: new Set(),
            timer: null, generation: 0, groupCurrent: new Map(), groupTimer: null,
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
        const navigation = event.type === 'click' && event.target.closest
            ? event.target.closest(GROUP_NAV) : null;
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
            controller.phase = null;
            controller.completed.clear();
            moveGroup(controller, group, navigation.dataset.adaAlarmGroupNavigation);
            return;
        }
        const card = event.target.closest && event.target.closest(CARD);
        if (!card || card.hidden || card.dataset.adaAlarmGrouped === 'true') {
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
        module.exports = {routePath, previewPlan, toggleSelection, groupChoice, nextGroupIndex, planIntegratedPositions};
    }
})();
