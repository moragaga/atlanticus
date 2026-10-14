'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const {test} = require('node:test');
const {affectionOutline} = require(path.join(__dirname,
    '../../src/ada/web/alarms/live_surface/resources/js/10-alarm-live-routes.js'));

test('affection follows the full pixel perimeter of both short and tall cards', () => {
    const short = affectionOutline(140, 80);
    const tall = affectionOutline(310, 710);
    assert.equal(short.length, 440);
    assert.equal(tall.length, 2040);
    assert.notEqual(short.length, tall.length);
    assert.equal(tall.d, 'M 156 1 H 311 V 711 H 1 V 1 H 156');
});

test('affection remains a closed traversal at each perimeter', () => {
    for (const [width, height] of [[20, 20], [100, 900], [400, 200]]) {
        const result = affectionOutline(width, height);
        const commands = result.d.split(' ');
        assert.equal(commands[1], commands.at(-1));
        assert.equal(result.length, 2 * (width + height));
    }
});
