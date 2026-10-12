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
