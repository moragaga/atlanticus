'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {
    routeGeometry, previewPlan, toggleSelection, groupChoice, nextGroupIndex,
    alarmGridColumn, markerKind, sortedPreviewCandidates, integratedGridColumn,
} = require(path.join(__dirname,
    '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));

test('trace makes an elevated horizontal junction between the card and the baseline', () => {
    assert.deepEqual(routeGeometry(120, 50, [{x: 700, y: 130}]).segments.map((part) => part.d), [
        'M 120 50 V 72', 'M 120 72 H 700', 'M 700 72 V 130',
    ]);
    assert.deepEqual(routeGeometry(700, 50, [{x: 120, y: 130}]).segments.map((part) => part.d), [
        'M 700 50 V 72', 'M 700 72 H 120', 'M 120 72 V 130',
    ]);
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

test('zoom keeps the original slot independently of whether its component is displayed', () => {
    const card = {dataset: {
        adaAlarmDisplayComponentKey: 'plant', adaAlarmDisplayScope: 'plant', adaAlarmSlot: '4',
    }};
    const minePoints = [{dataset: {
        adaComponentKey: 'mine', adaScope: 'mine', adaAlarmBaselineRegion: 'main',
    }}];
    assert.equal(alarmGridColumn(card, minePoints, true, 'mine'), '4');
});

test('component IDs position the two live alarms in columns one and seven', () => {
    const components = [
        ['cmp_general_mina_6df268db211b', 'mine'],
        ['cmp_carguio_4cbd52aaa4b0', 'mine'],
        ['cmp_transporte_67b979e9ab49', 'mine'],
        ['cmp_chancado_stmg_abd7384135fd', 'mine'],
        ['cmp_stockpile_chacay_4265300400b1', 'plant'],
        ['cmp_molienda_e3aaacbeb627', 'plant'],
        ['cmp_flotacion_9bbf64c07ea7', 'plant'],
        ['cmp_transporte_de_fluidos_823d86d77b46', 'plant'],
        ['cmp_puerto_9f4e782f8c6a', 'plant'],
    ];
    const points = components.map(([adaComponentKey, adaScope]) => ({dataset: {
        adaComponentKey, adaScope, adaAlarmBaselineRegion: 'main',
    }}));
    const mp10 = {dataset: {adaAlarmSlot: '1', adaAlarmDisplayComponentKey: components[0][0],
        adaAlarmDisplayScope: 'mine'}};
    const tk = {dataset: {adaAlarmSlot: '4', adaAlarmDisplayComponentKey: components[6][0],
        adaAlarmDisplayScope: 'plant'}};
    assert.equal(integratedGridColumn(mp10, points), 1);
    assert.equal(integratedGridColumn(tk, points), 7);
    assert.equal(integratedGridColumn({dataset: {adaAlarmDisplayComponentKey: 'unknown',
        adaAlarmDisplayScope: 'plant'}}, points), null);
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
