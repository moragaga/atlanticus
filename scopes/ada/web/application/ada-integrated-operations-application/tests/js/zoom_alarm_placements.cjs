'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');

global.document = {addEventListener() {}, documentElement: {}};
global.window = {addEventListener() {}};
global.MutationObserver = class {observe() {}};

const {resolveZoomAlarmPlacements} = require(path.join(__dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/js/10_presentation.js'));

function card(key, scope, slot) {
    return {dataset: {adaAlarmDisplayComponentKey: key, adaAlarmDisplayScope: scope,
        adaAlarmSlot: String(slot)}};
}
function point(key) {
    return {dataset: {adaComponentKey: key}};
}

test('Mine zoom reserves full component-width columns and retains Plant alarms', () => {
    const mine = card('general', 'mine', 1);
    const plant = card('flotacion', 'plant', 4);
    const plan = resolveZoomAlarmPlacements([mine, plant],
        [point('general'), point('carguio'), point('transporte'), point('chancado')], 'mine');
    assert.equal(plan.count, 4);
    assert.equal(plan.entries.find((entry) => entry.card === mine).column, 1);
    assert.equal(plan.entries.find((entry) => entry.card === plant).column, 4);
    assert.equal(plan.entries.length, 2);
});

test('Plant zoom follows its component and moves Mine alarm to opposite edge', () => {
    const mine = card('general', 'mine', 1);
    const plant = card('flotacion', 'plant', 4);
    const plan = resolveZoomAlarmPlacements([mine, plant],
        [point('stockpile'), point('molienda'), point('flotacion'), point('fluidos'), point('puerto')],
        'plant');
    assert.equal(plan.count, 5);
    assert.equal(plan.entries.find((entry) => entry.card === mine).column, 1);
    assert.equal(plan.entries.find((entry) => entry.card === plant).column, 3);
});

test('Zoom never overlaps cards when their preferred columns collide', () => {
    const cards = Array.from({length: 6}, (_, i) => card('general', 'mine', i + 1));
    const plan = resolveZoomAlarmPlacements(cards,
        [point('general'), point('carguio'), point('transporte'), point('chancado')], 'mine');
    assert.equal(plan.count, 6);
    assert.deepEqual(new Set(plan.entries.map((entry) => entry.column)).size, 6);
    assert.equal(plan.entries.length, 6);
});
