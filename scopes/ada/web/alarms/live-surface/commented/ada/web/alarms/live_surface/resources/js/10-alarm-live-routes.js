(() => {
    'use strict';

    const SURFACE = '.ada-alarm-live-surface';
    const BOARD = '.ada-alarm-live-board';
    const CARD = '.ada-alarm-live-card';
    const POINT = '.ada-alarm-baseline-surface__point';
    const ROUTES = '.ada-alarm-live-routes';
    const ROUTE = '.ada-alarm-live-route';
    const MARKER = '.ada-alarm-live-marker';
    const COMPONENT = '.ada-card-display[data-ada-subcomponent-key], .ada-card-display__region[data-ada-subcomponent-key]';
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
    const controllers = new WeakMap();
    const scheduled = new WeakSet();

    function keys(value) {
        return new Set((value || '').split(/\s+/).filter(Boolean));
    }

    function targetAddresses(value) {
        try {
            const addresses = JSON.parse(value || '[]');
            return Array.isArray(addresses)
                ? addresses.filter((item) => Array.isArray(item) && item.length === 2
                    && item.every((key) => typeof key === 'string' && key.length > 0))
                : [];
        } catch (_) {
            return [];
        }
    }

    function routeTargetKeys(card) {
        const targets = keys(card.dataset.adaAlarmTargetComponents);
        targetAddresses(card.dataset.adaAlarmTargetAddresses)
            .forEach(([owner]) => targets.add(owner));
        return targets;
    }

    function revealArrivalMs(index, count) {
        return Math.round(PREVIEW.revealMs * (.55 + .18 * (index + 1) / count));
    }

    function nextCycleAfterSelection(candidates, selected) {
        const index = candidates.indexOf(selected);
        return index < 0 || index === candidates.length - 1
            ? new Set()
            : new Set(candidates.slice(0, index + 1));
    }

    function visible(element) {
        return !element.hidden && element.getClientRects().length > 0;
    }

    function center(rect, origin) {
        return rect.left - origin.left + rect.width / 2;
    }

    // Dibuja el recorrido ortogonal y reserva el último tramo para la llegada al punto.
    function routeGeometry(fromX, fromY, targets) {
        if (!targets.length) {
            return {segments: [], arrivals: []};
        }
        fromX = Math.round(fromX);
        fromY = Math.round(fromY);
        targets = targets.map((target) => ({
            ...target, x: Math.round(target.x), y: Math.round(target.y),
        }));
        const bottom = Math.min(...targets.map((target) => target.y));
        const junction = Math.round(fromY + (bottom - fromY) * .28);
        const left = Math.min(fromX, ...targets.map((target) => target.x));
        const right = Math.max(fromX, ...targets.map((target) => target.x));
        const local = right - left < 1;
        const segments = [];
        const add = (d, length, delay, duration) => {
            if (length > 0) {
                segments.push({d, length, delay, duration});
            }
        };
        const arrivals = targets.map((target, index) => revealArrivalMs(index, targets.length));
        if (local) {
            const end = Math.max(...targets.map((target) => target.y));
            const duration = revealArrivalMs(targets.length - 1, targets.length);
            add(`M ${fromX} ${fromY} V ${end}`, end - fromY, 0, duration);
            targets.forEach((target, index) => {
                arrivals[index] = Math.round(duration * (target.y - fromY) / (end - fromY));
            });
        } else {
            add(`M ${fromX} ${fromY} V ${junction}`, junction - fromY, 0, 600);
            add(`M ${fromX} ${junction} H ${left}`, fromX - left, 600, 1400);
            add(`M ${fromX} ${junction} H ${right}`, right - fromX, 600, 1400);
        }
        if (!local) {
            targets.forEach((target, index) => add(
                `M ${target.x} ${junction} V ${target.y}`,
                target.y - junction, 2000, arrivals[index] - 2000,
            ));
        }
        return {segments, arrivals};
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


    // Los slots 1–3 y 4–6 expresan la vista del operador; la columna sale del ID del componente.
    function integratedGridColumn(card, points) {
        const key = card.dataset.adaAlarmDisplayComponentKey;
        const scope = card.dataset.adaAlarmDisplayScope;
        const index = points.findIndex((point) => point.dataset.adaComponentKey === key
            && point.dataset.adaScope === scope && point.dataset.adaAlarmBaselineRegion === 'main');
        return key && index >= 0 ? index + 1 : null;
    }

    function resolveIntegratedPresentation(points, baselineScope) {
        const scopes = new Set(points.map((point) => point.dataset.adaScope));
        if (scopes.has('mine') && scopes.has('plant')) {
            return 'overview';
        }
        return (baselineScope === 'mine' || baselineScope === 'plant')
            && scopes.has(baselineScope) ? baselineScope : 'overview';
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

    // Overview usa la columna de su componente; Mine y Plant conservan todos los slots como pills.
    function alarmGridColumn(card, points, integrated, presentation) {
        const column = integrated && presentation === 'overview'
            ? integratedGridColumn(card, points) : null;
        return String(column || Number(card.dataset.adaAlarmSlot) || 1);
    }

    function integratedPosition(board, cards, points, integrated, presentation) {
        if (integrated) {
            board.dataset.adaAlarmLayout = 'integrated';
            board.dataset.adaAlarmPresentation = presentation;
        } else {
            delete board.dataset.adaAlarmLayout;
            delete board.dataset.adaAlarmPresentation;
        }
        cards.filter((card) => card.parentElement === board).forEach((card) => {
            if (card.dataset.adaAlarmPositioned === 'true') {
                delete card.dataset.adaAlarmPositioned;
                card.style.removeProperty('--ada-alarm-live-display-x');
                card.style.removeProperty('--ada-alarm-live-display-width');
            }
            const column = alarmGridColumn(card, points, integrated, presentation);
            if (card.style.gridColumn !== column) {
                card.style.gridColumn = column;
            }
        });
    }

    // Inyecta las dos mitades del recorrido como hijo exterior, nunca dentro del overlay de contenido.
    // El recorrido usa píxeles efectivos para que nunca avance una cola móvil.
    function affectionOutline(width, height) {
        const w = Math.max(2, Math.round(width));
        const h = Math.max(2, Math.round(height));
        const middle = (w + 2) / 2;
        return {
            width: w + 2, height: h + 2, length: 2 * (w + h),
            d: `M ${middle} 1 H ${w + 1} V ${h + 1} H 1 V 1 H ${middle}`,
        };
    }

    function ensureAffectionTrace(component) {
        let svg = component.querySelector(':scope > .ada-alarm-live-affection-trace');
        if (!svg) {
            svg = document.createElementNS(NS, 'svg');
            svg.setAttribute('class', 'ada-alarm-live-affection-trace');
            svg.setAttribute('preserveAspectRatio', 'none');
            svg.setAttribute('aria-hidden', 'true');
            svg.appendChild(document.createElementNS(NS, 'path'));
            component.appendChild(svg);
        }
        const rect = component.getBoundingClientRect();
        const outline = affectionOutline(rect.width, rect.height);
        const size = `${outline.width}:${outline.height}`;
        if (svg.dataset.adaAlarmAffectionSize !== size) {
            svg.dataset.adaAlarmAffectionSize = size;
            svg.setAttribute('viewBox', `0 0 ${outline.width} ${outline.height}`);
            svg.querySelector('path').setAttribute('d', outline.d);
            svg.style.setProperty('--ada-alarm-live-affection-length', `${outline.length}px`);
        }
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
        const origin = overlay.getBoundingClientRect();
        const width = Math.max(1, origin.width);
        const height = Math.max(1, origin.height);
        const definitions = [];
        const markerDefinitions = [];
        const arrivals = new Map();
        const visibleCards = cards.filter(visible);
        visibleCards.forEach((card) => {
            if (card.dataset.adaAlarmGrouped === 'true') {
                return;
            }
            const targetKeys = routeTargetKeys(card);
            const occurrence = card.dataset.adaAlarmOccurrenceId;
            const tone = card.dataset.adaAlarmColor;
            if (!targetKeys.size || (tone !== 'RED' && tone !== 'YELLOW')) {
                return;
            }
            const cardRect = card.getBoundingClientRect();
            const fromX = center(cardRect, origin);
            const fromY = cardRect.bottom - origin.top;
            const originComponent = card.dataset.adaAlarmDisplayComponentKey;
            const originScope = card.dataset.adaAlarmDisplayScope;
            const targets = points.filter((point) => targetKeys.has(point.dataset.adaComponentKey));
            const destinations = targets.map((point) => {
                const rect = point.getBoundingClientRect();
                return {point, x: center(rect, origin), y: rect.top - origin.top + rect.height / 2};
            }).filter((destination) => destination.y > fromY);
            const geometry = routeGeometry(fromX, fromY, destinations);
            geometry.segments.forEach((segment) => definitions.push({occurrence, tone, ...segment}));
            destinations.forEach(({point}, index) => {
                const arrival = geometry.arrivals[index];
                const isOrigin = originComponent === point.dataset.adaComponentKey
                    && originScope === point.dataset.adaScope;
                markerDefinitions.push({
                    occurrence, tone, point, arrival,
                    kind: markerKind(isOrigin, destinations.length),
                });
                arrivals.set(JSON.stringify([occurrence, point.dataset.adaComponentKey]), arrival);
            });
        });
        const signature = [width, height,
            ...definitions.map((item) => `${item.occurrence}|${item.tone}|${item.d}`),
            ...markerDefinitions.map((item) => `${item.occurrence}|${item.kind}|${item.arrival}`),
        ].join('||');
        const topology = [
            ...definitions.map((item) => `${item.occurrence}|${item.tone}`),
            ...markerDefinitions.map((item) =>
                `${item.occurrence}|${item.tone}|${item.kind}|${item.point.dataset.adaComponentKey}`),
        ].join('||');
        const sameAnchors = controller.anchorNodes.length === points.length
            && points.every((point, index) => controller.anchorNodes[index] === point);
        const previousPaths = [...overlay.querySelectorAll(ROUTE)];
        const previousSvg = overlay.querySelector('svg');
        const sameTopology = Boolean(previousSvg) && sameAnchors
            && controller.routeTopology === topology
            && previousPaths.length === definitions.length
            && surface.querySelectorAll(MARKER).length === markerDefinitions.length;
        if (signature !== controller.geometrySignature || !sameTopology) {
            if (sameTopology) {
                previousSvg.setAttribute('viewBox', `0 0 ${width} ${height}`);
                definitions.forEach(({d, length, delay, duration}, index) => {
                    const path = previousPaths[index];
                    path.setAttribute('d', d);
                    path.style.setProperty('--ada-alarm-live-route-length', `${length}px`);
                    path.style.setProperty('--ada-alarm-live-route-delay', `${delay}ms`);
                    path.style.setProperty('--ada-alarm-live-route-duration', `${duration}ms`);
                });
                markerDefinitions.forEach(({occurrence, point, arrival}) => {
                    const marker = [...point.querySelectorAll(MARKER)].find((item) =>
                        item.dataset.adaAlarmOccurrenceId === occurrence);
                    marker.style.setProperty('--ada-alarm-live-marker-delay', `${arrival}ms`);
                });
            } else {
                const svg = document.createElementNS(NS, 'svg');
                svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
                svg.setAttribute('preserveAspectRatio', 'none');
                svg.setAttribute('aria-hidden', 'true');
                definitions.forEach(({occurrence, tone, d, length, delay, duration}) => {
                    const path = document.createElementNS(NS, 'path');
                    path.setAttribute('d', d);
                    path.setAttribute('class', `ada-alarm-live-route ada-alarm-live-route--${tone.toLowerCase()}`);
                    path.dataset.adaAlarmOccurrenceId = occurrence;
                    path.dataset.adaAlarmFocus = 'idle';
                    svg.appendChild(path);
                    path.style.setProperty('--ada-alarm-live-route-length', `${length}px`);
                    path.style.setProperty('--ada-alarm-live-route-delay', `${delay}ms`);
                    path.style.setProperty('--ada-alarm-live-route-duration', `${duration}ms`);
                });
                points.forEach((point) => point.querySelectorAll(MARKER).forEach((marker) => marker.remove()));
                markerDefinitions.forEach(({occurrence, tone, point, kind, arrival}) => {
                    const marker = addMarker(point, occurrence, tone, kind);
                    marker.style.setProperty('--ada-alarm-live-marker-delay', `${arrival}ms`);
                });
                overlay.replaceChildren(svg);
            }
            controller.geometrySignature = signature;
            controller.routeTopology = topology;
            controller.anchorNodes = [...points];
        }
        controller.cards = cards;
        controller.points = points;
        controller.paths = [...overlay.querySelectorAll(ROUTE)];
        controller.markers = [...surface.querySelectorAll(MARKER)];
        controller.arrivals = arrivals;
        controller.candidates = sortedPreviewCandidates(cards, controller.paths, integrated);
    }

    // Conserva la dirección owner/subcomponent y pinta el borde incluso si el punto no está visible.
    function updateAffections(controller) {
        const application = controller.surface.closest('#ada-generic-application');
        if (!application) {
            return;
        }
        const focused = controller.selected || controller.active;
        const card = controller.cards.find((item) => visible(item)
            && item.dataset.adaAlarmOccurrenceId === focused);
        const color = card && card.dataset.adaAlarmColor;
        const addresses = card ? targetAddresses(card.dataset.adaAlarmTargetAddresses) : [];
        const phase = controller.selected ? 'selected' : controller.phase;
        application.querySelectorAll(COMPONENT).forEach((component) => {
            const owner = component.dataset.adaComponentKey
                || component.closest('[data-ada-component-key]')?.dataset.adaComponentKey;
            const subcomponent = component.dataset.adaSubcomponentKey;
            const arrival = controller.arrivals.get(JSON.stringify([focused, owner]));
            const affected = addresses.some(([key, subkey]) =>
                key === owner && subkey === subcomponent);
            if (affected && (color === 'RED' || color === 'YELLOW')) {
                ensureAffectionTrace(component);
                component.dataset.adaAlarmAffection = color.toLowerCase();
                component.dataset.adaAlarmPhase = phase;
                const delay = arrival === undefined ? revealArrivalMs(0, 1) : arrival;
                component.style.setProperty('--ada-alarm-live-affection-delay', `${delay}ms`);
            } else {
                delete component.dataset.adaAlarmAffection;
                delete component.dataset.adaAlarmPhase;
                component.style.removeProperty('--ada-alarm-live-affection-delay');
            }
            if (affected && phase !== 'reveal' && phase !== 'fade') {
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
        if (plan.mode === 'steady') {
            controller.active = plan.key;
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
        if (controller.candidates.length === 1) {
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
        const previous = controller.selected;
        stopTimer(controller);
        controller.selected = next;
        controller.active = null;
        controller.phase = 'idle';
        controller.completed = next
            ? new Set()
            : nextCycleAfterSelection(controller.candidates, previous);
        reconcile(controller);
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
        const presentation = integrated
            ? resolveIntegratedPresentation(points, baseline.dataset.adaIoScope) : 'overview';
        integratedPosition(board, cards, points, integrated, presentation);
        buildGeometry(controller, board, cards, points, integrated);
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
        const controller = {
            surface, cards: [], points: [], paths: [], markers: [], candidates: [],
            selected: null, active: null, phase: 'idle', completed: new Set(),
            timer: null, generation: 0, geometrySignature: null, routeTopology: null, anchorNodes: [],
            arrivals: new Map(),
            groupCurrent: new Map(),
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
            const baseline = surface.querySelector('.ada-alarm-baseline-surface');
            const overlay = surface.querySelector(ROUTES);
            if (baseline) {
                resize.observe(baseline);
            }
            if (overlay) {
                resize.observe(overlay);
            }
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
        window.addEventListener('scroll', () => document.querySelectorAll(SURFACE).forEach(schedule), true);
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
            routeGeometry, previewPlan, toggleSelection, groupChoice, nextGroupIndex,
            alarmGridColumn, integratedPosition, markerKind, sortedPreviewCandidates,
            targetAddresses, routeTargetKeys, revealArrivalMs, nextCycleAfterSelection,
            resolveIntegratedPresentation, integratedGridColumn, affectionOutline,
        };
    }
})();
