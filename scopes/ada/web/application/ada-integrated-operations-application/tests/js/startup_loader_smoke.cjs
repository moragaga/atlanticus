const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.resolve(__dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/js/05_startup_loader.js'), 'utf8');

function fixture({count = 9, ready = 0, globals = false, alarms = false, time = false, route = '/'} = {}) {
    const frames = [];
    const observers = [];
    const reasons = [];
    const areas = Array.from({length: count}, (_, i) => ({
        getAttribute: (key) => key === 'data-ready' ? (i < ready ? 'true' : 'false') : null,
    }));
    const dashboard = {querySelectorAll: () => areas};
    const indicator = {getAttribute: () => globals ? 'true' : 'false'};
    const board = {getAttribute: () => alarms ? 'true' : 'false'};
    const clock = {getAttribute: () => time ? 'true' : 'false'};
    const elements = {
        'ada-io-startup-loader': {},
        'ada-integrated-operations-dashboard': dashboard,
        'ada-operational-header-global-indicators-slot': indicator,
        'ada-alarm-live-board': board,
    };
    const document = {
        body: {}, addEventListener() {},
        getElementById: (id) => elements[id] || null,
        querySelector: () => clock,
    };
    const window = {
        requestAnimationFrame: (fn) => frames.push(fn),
        adaIoFinishStartupLoader: (reason) => {reasons.push(reason); window.adaIoStopStartupObservers?.();},
    };
    class Observer {
        constructor(fn) {this.fn = fn; this.active = false; observers.push(this);}
        observe(_target, _options) {this.active = true;}
        disconnect() {this.active = false;}
    }
    vm.runInNewContext(script, {window, document, location: {pathname: route}, MutationObserver: Observer});
    function flush() {let safety = 20; while (frames.length && safety--) frames.shift()(); assert.ok(safety > 0);}
    function notify() {observers.filter(o => o.active).forEach(o => o.fn());}
    return {flush, reasons, observers,
        readyAreas: () => {ready = count; notify();},
        readyGlobal: () => {globals = true; notify();},
        readyAlarm: () => {alarms = true; notify();},
        readyTime: () => {time = true; notify();},
    };
}
{
    const p = fixture(); p.flush();
    assert.deepEqual(p.reasons, []);
    p.readyAreas(); p.flush(); assert.deepEqual(p.reasons, []);
    p.readyGlobal(); p.flush(); assert.deepEqual(p.reasons, []);
    p.readyAlarm(); p.flush(); assert.deepEqual(p.reasons, []);
    p.readyTime(); p.flush(); assert.deepEqual(p.reasons, ['ready']);
    assert.equal(p.observers.length, 1);
    assert.equal(p.observers[0].active, false);
}
{
    const p = fixture({count: 8, ready: 8, globals: true, alarms: true, time: true});
    p.flush(); assert.deepEqual(p.reasons, []);
}
{
    const p = fixture({route: '/manager'}); p.flush();
    assert.equal(p.observers.length, 0);
}
{
    const p = fixture({ready: 9, globals: true, alarms: true, time: true}); p.flush();
    assert.deepEqual(p.reasons, ['ready']);
}
console.log('Startup loader: one-shot readiness and disconnected observer OK');
