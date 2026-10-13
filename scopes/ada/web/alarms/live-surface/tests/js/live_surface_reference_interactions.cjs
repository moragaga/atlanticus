'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {
    routePath, previewPlan, toggleSelection, groupChoice, nextGroupIndex,
    planIntegratedPositions, markerKind, sortedPreviewCandidates,
} = require(path.join(__dirname,
    '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));

test('trace makes an elevated horizontal junction between the card and the baseline', () => {
    assert.equal(routePath(120, 50, 700, 130, 72.4), 'M 120 50 V 72.4 H 700 V 130');
    assert.equal(routePath(700, 50, 120, 130, 72.4), 'M 700 50 V 72.4 H 120 V 130');
});

test('a single live alarm keeps its highlighted route without cycling', () => {
    assert.deepEqual(previewPlan(['occ-mp10'], new Set(['occ-mp10'])), {
        mode: 'steady', key: 'occ-mp10',
    });
});

test('automatic preview visits each candidate before the next cycle', () => {
    const candidates = ['occ-a', 'occ-b', 'occ-c'];
    assert.deepEqual(previewPlan(candidates, new Set(['occ-a'])), {
        mode: 'cycle', key: 'occ-b',
    });
    assert.deepEqual(previewPlan(candidates, new Set(candidates)), {
        mode: 'pause', key: null,
    });
});

test('manual selection persists until toggled and ignores absent alarms', () => {
    assert.equal(toggleSelection(null, 'occ-a', ['occ-a', 'occ-b']), 'occ-a');
    assert.equal(toggleSelection('occ-a', 'stale', ['occ-a']), 'occ-a');
    assert.equal(toggleSelection('occ-a', 'occ-a', ['occ-a']), null);
});

test('chevrons reflect origin, destination and a local closed circuit', () => {
    assert.equal(markerKind(true, 1), 'contract');
    assert.equal(markerKind(true, 2), 'up');
    assert.equal(markerKind(false, 2), 'down');
});

test('distributed group retains the projected order and wraps navigation', () => {
    assert.equal(groupChoice(['MINE:a', 'PLANT:b'], 'PLANT:b'), 1);
    assert.equal(nextGroupIndex(3, 0, 'previous'), 2);
    assert.equal(nextGroupIndex(3, 2, 'next'), 0);
});

test('integrated cards align to their process point without overlap', () => {
    const layout = planIntegratedPositions([
        {key: 'plant', x: 900}, {key: 'mine', x: 150},
    ], 1200);
    assert.deepEqual(layout.map((item) => item.key), ['mine', 'plant']);
    assert.ok(layout.every((item) => item.width > 0 && item.width <= 196));
    assert.equal(planIntegratedPositions([
        {key: 'a', x: 50}, {key: 'b', x: 50},
    ], 1200), null);
});

test('preview candidates follow tone priority unless integrated layout uses geometry', () => {
    const cards = [
        {dataset: {adaAlarmOccurrenceId: 'yellow', adaAlarmColor: 'YELLOW',
            adaAlarmGrouped: 'false'}, hidden: false, getClientRects: () => [1],
            getBoundingClientRect: () => ({left: 30})},
        {dataset: {adaAlarmOccurrenceId: 'red', adaAlarmColor: 'RED',
            adaAlarmGrouped: 'false'}, hidden: false, getClientRects: () => [1],
            getBoundingClientRect: () => ({left: 90})},
    ];
    const routes = ['yellow', 'red'].map((key) => ({
        dataset: {adaAlarmOccurrenceId: key},
    }));
    assert.deepEqual(sortedPreviewCandidates(cards, routes, false), ['red', 'yellow']);
    assert.deepEqual(sortedPreviewCandidates(cards, routes, true), ['yellow', 'red']);
});
