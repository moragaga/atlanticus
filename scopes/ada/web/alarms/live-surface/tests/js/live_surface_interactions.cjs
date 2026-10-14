'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {
    routeGeometry,
    previewPlan,
    toggleSelection,
} = require(path.join(__dirname,
    '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));

test('route shares its trunk and reveals branches after reaching it', () => {
    const geometry = routeGeometry(50, 20, [{x: 10, y: 80}, {x: 90, y: 80}]);
    assert.deepEqual(geometry.segments.map((part) => part.d), [
        'M 50 20 V 37', 'M 50 37 H 10', 'M 50 37 H 90',
        'M 10 37 V 80', 'M 90 37 V 80',
    ]);
    assert.deepEqual(geometry.segments.map((part) => part.delay), [0, 600, 600, 2000, 2000]);
    assert.ok(geometry.arrivals[0] < geometry.arrivals[1]);
    assert.deepEqual(routeGeometry(50, 20, [{x: 50, y: 80}]).segments.map((part) => part.d), [
        'M 50 20 V 80',
    ]);
});

test('route endpoints align to whole pixels across cards and baseline points', () => {
    const route = routeGeometry(125.45, 150.42, [{x: 543.27, y: 170.66}]);
    assert.deepEqual(route.segments.map((part) => part.d), [
        'M 125 150 V 156', 'M 125 156 H 543', 'M 543 156 V 171',
    ]);
});

test('manual selection toggles the same occurrence and rejects stale occurrences', () => {
    const available = ['occ-a', 'occ-b'];
    assert.equal(toggleSelection(null, 'occ-a', available), 'occ-a');
    assert.equal(toggleSelection('occ-a', 'occ-a', available), null);
    assert.equal(toggleSelection('occ-a', 'occ-b', available), 'occ-b');
    assert.equal(toggleSelection('occ-a', 'removed-occurrence', available), 'occ-a');
});

test('the preview stays stable for a single routed alarm', () => {
    assert.deepEqual(previewPlan([], new Set()), {mode: 'idle', key: null});
    assert.deepEqual(previewPlan(['occ-a'], new Set(['occ-a'])), {
        mode: 'steady', key: 'occ-a',
    });
});

test('the preview visits each available occurrence and pauses before the next cycle', () => {
    const available = ['occ-b', 'occ-a', 'occ-c'];
    assert.deepEqual(previewPlan(available, new Set()), {mode: 'cycle', key: 'occ-b'});
    assert.deepEqual(previewPlan(available, new Set(['occ-b'])), {
        mode: 'cycle', key: 'occ-a',
    });
    assert.deepEqual(previewPlan(available, new Set(['occ-b', 'occ-a'])), {
        mode: 'cycle', key: 'occ-c',
    });
    assert.deepEqual(previewPlan(available, new Set(available)), {
        mode: 'pause', key: null,
    });
});

test('deselecting resumes at the next visible alarm and wraps after the last', () => {
    const {nextCycleAfterSelection, previewPlan} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    const candidates = ['occ-a', 'occ-b', 'occ-c'];
    assert.deepEqual(previewPlan(candidates,
        nextCycleAfterSelection(candidates, 'occ-b')), {mode: 'cycle', key: 'occ-c'});
    assert.deepEqual(previewPlan(candidates,
        nextCycleAfterSelection(candidates, 'occ-c')), {mode: 'cycle', key: 'occ-a'});
});

test('affected subcomponents retain their owner and reveal after their route', () => {
    const {targetAddresses, routeTargetKeys, revealArrivalMs} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    assert.deepEqual(targetAddresses('[["cmp-a","shared"],["cmp-b","shared"]]'), [
        ['cmp-a', 'shared'], ['cmp-b', 'shared'],
    ]);
    assert.deepEqual(targetAddresses('{invalid'), []);
    assert.deepEqual([...routeTargetKeys({dataset: {
        adaAlarmTargetComponents: 'cmp-a',
        adaAlarmTargetAddresses: '[["cmp-b","shared"]]',
    }})], ['cmp-a', 'cmp-b']);
    assert.ok(revealArrivalMs(0, 2) < revealArrivalMs(1, 2));
    assert.ok(revealArrivalMs(1, 2) + 950 < 4000);
});

test('distributed carousel preserves an active occurrence when the store reorders members', () => {
    const {groupChoice} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    assert.equal(groupChoice(['MINE:a', 'PLANT:b'], 'PLANT:b'), 1);
    assert.equal(groupChoice(['PLANT:b', 'MINE:a'], 'PLANT:b'), 0);
    assert.equal(groupChoice(['MINE:a'], 'PLANT:b'), 0);
});

test('distributed carousel navigates in the projected order and wraps without re-ranking', () => {
    const {nextGroupIndex} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    assert.equal(nextGroupIndex(3, 0, 'next'), 1);
    assert.equal(nextGroupIndex(3, 2, 'next'), 0);
    assert.equal(nextGroupIndex(3, 0, 'previous'), 2);
    assert.equal(nextGroupIndex(1, 0, 'next'), 0);
});


test('integrated placement aligns to components without overlapping card bounds', () => {
    const {planIntegratedPositions} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    const positions = planIntegratedPositions([
        {key: 'plant-a', x: 810}, {key: 'mine-a', x: 75},
        {key: 'mine-b', x: 150}, {key: 'plant-b', x: 840},
    ], 1200);
    assert.deepEqual(positions.map((item) => item.key), [
        'mine-a', 'mine-b', 'plant-a', 'plant-b',
    ]);
    for (let i = 0; i < positions.length; i += 1) {
        const item = positions[i];
        assert.ok(item.width > 0 && item.width <= 196);
        assert.ok(item.x - item.width / 2 >= 0);
        assert.ok(item.x + item.width / 2 <= 1200);
        if (i > 0) {
            const previous = positions[i - 1];
            assert.ok(previous.x + previous.width / 2 + 4 <= item.x - item.width / 2);
        }
    }
});

test('overview uses nine component widths while zoom retains pill width per area', () => {
    const {planIntegratedPositions, integratedCardVisible} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    const entries = [{key: 'mine-a', x: 70}, {key: 'plant-a', x: 900}];
    const overview = planIntegratedPositions(entries, 1260, 9, true);
    const zoom = planIntegratedPositions([{key: 'mine-a', x: 150}], 1260, 4, false);
    assert.equal(overview[0].width, 136);
    assert.equal(zoom[0].width, 206);
    assert.equal(integratedCardVisible('mine', 'overview'), true);
    assert.equal(integratedCardVisible('plant', 'mine'), false);
    assert.equal(integratedCardVisible('plant', 'plant'), true);
});

test('nine visible points keep both area alarms in the overview', () => {
    const {resolveIntegratedPresentation, integratedCardVisible} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    const points = [
        {dataset: {adaScope: 'mine'}},
        {dataset: {adaScope: 'plant'}},
    ];
    const presentation = resolveIntegratedPresentation(points, 'mine');
    assert.equal(presentation, 'overview');
    assert.equal(integratedCardVisible('plant', presentation), true);
    assert.equal(resolveIntegratedPresentation(points.slice(0, 1), 'mine'), 'mine');
    assert.equal(resolveIntegratedPresentation(points.slice(1), 'plant'), 'plant');
});

test('two visible routed cards enter the visual rotation in component order', () => {
    const {sortedPreviewCandidates} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    const cards = [
        {hidden: false, dataset: {adaAlarmOccurrenceId: 'occ-mp10', adaAlarmColor: 'YELLOW'},
            getClientRects: () => [{}], getBoundingClientRect: () => ({left: 120})},
        {hidden: false, dataset: {adaAlarmOccurrenceId: 'occ-tk050', adaAlarmColor: 'RED'},
            getClientRects: () => [{}], getBoundingClientRect: () => ({left: 1390})},
    ];
    const paths = cards.map((card) => ({dataset: {
        adaAlarmOccurrenceId: card.dataset.adaAlarmOccurrenceId,
    }}));
    const candidates = sortedPreviewCandidates(cards, paths, true);
    assert.deepEqual(candidates, ['occ-mp10', 'occ-tk050']);
    assert.deepEqual(previewPlan(candidates, new Set(['occ-mp10'])), {
        mode: 'cycle', key: 'occ-tk050',
    });
});

test('integrated placement refuses unresolved or colliding geometries', () => {
    const {planIntegratedPositions} = require(path.join(__dirname,
        '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));
    assert.equal(planIntegratedPositions([{key: 'a', x: 30}], 0), null);
    assert.equal(planIntegratedPositions([
        {key: 'a', x: 20}, {key: 'b', x: 20},
    ], 600), null);
    assert.equal(planIntegratedPositions([
        {key: 'a', x: 0},
    ], 600), null);
});
