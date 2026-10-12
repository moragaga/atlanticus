'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {
    routePath,
    previewPlan,
    toggleSelection,
} = require(path.join(__dirname,
    '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));

test('route remains anchored from the card to the affected process', () => {
    assert.equal(routePath(10, 20, 70, 80), 'M 10 20 V 47 H 70 V 80');
    assert.equal(routePath(70, 20, 10, 80), 'M 70 20 V 47 H 10 V 80');
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
