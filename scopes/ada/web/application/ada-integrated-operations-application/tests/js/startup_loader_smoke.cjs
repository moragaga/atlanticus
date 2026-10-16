const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.resolve(__dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/js/05_startup_loader.js'), 'utf8');

function fixture({mode = 'normal', ready = 0, mounted = true, globals = false,
    alarms = false, time = false, count = 9, route = '/'} = {}) {
    const frames = [];
    const observers = [];
    const reasons = [];
    const appAttrs = {'data-ada-content-state-presentation': mode};
    const areas = Array.from({length: count}, (_, i) => ({
        getAttribute: (name) => name === 'data-ready' ? (i < ready ? 'true' : 'false')
            : name === 'data-ada-io-component-key' ? `area_${i}` : null,
    }));
    const parent = {};
    const dashboard = {querySelectorAll: () => areas};
    const indicator = {getAttribute: (name) => name === 'data-ready' && globals ? 'true' : 'false'};
    const board = {getAttribute: (name) => name === 'data-ready' && alarms ? 'true' : 'false'};
    const clock = {getAttribute: (name) => name === 'data-ready' && time ? 'true' : 'false'};
    let app = null;
    if (mounted) app = {
        parentNode: parent,
        getAttribute: (name) => appAttrs[name] || null,
        setAttribute: (name, value) => {appAttrs[name] = value;},
        contains: (node) => [dashboard, indicator, board].includes(node),
        querySelector: () => clock,
    };
    const elements = {
        'ada-io-startup-loader': {},
        'ada-integrated-operations-dashboard': dashboard,
        'ada-operational-header-global-indicators-slot': indicator,
        'ada-alarm-live-board': board,
    };
    const document = {
        body: {},
        addEventListener() {},
        getElementById: (id) => id === 'ada-generic-application' ? app : elements[id] || null,
    };
    const window = {
        requestAnimationFrame: (fn) => frames.push(fn),
        adaIoFinishStartupLoader: (reason) => {reasons.push(reason); window.adaIoStopStartupObservers?.();},
    };
    class Observer {
        constructor(fn) {this.fn = fn; this.active = false; observers.push(this);}
        observe(target, options) {this.active = true; this.target = target; this.options = options;}
        disconnect() {this.active = false;}
    }
    vm.runInNewContext(script, {window, document, location: {pathname: route}, MutationObserver: Observer});
    function flush() {let remaining = 20; while (frames.length && remaining--) frames.shift()(); assert.ok(remaining > 0);}
    function notify() {observers.filter(o => o.active).forEach(o => o.fn());}
    return {
        flush, notify, reasons, appAttrs, observers, window,
        setReady: (n) => {ready = n; notify();},
        setGlobal: () => {globals = true; notify();},
        setAlarm: () => {alarms = true; notify();},
        setTime: () => {time = true; notify();},
        replaceApp: () => {app = {...app, parentNode: parent}; notify();},
    };
}

{
    const p = fixture(); p.flush();
    assert.deepEqual(p.reasons, []);
    assert.equal(Array.from(p.window.adaIoStartupPending()).length, 12);
    p.setReady(9); p.flush();
    assert.deepEqual(Array.from(p.window.adaIoStartupPending()),
        ['global_indicators', 'alarms_render', 'time_status']);
    p.setGlobal(); p.flush(); assert.deepEqual(p.reasons, []);
    p.setAlarm(); p.flush(); assert.deepEqual(p.reasons, []);
    p.setTime(); p.flush(); assert.deepEqual(p.reasons, ['ready']);
    assert.equal(p.observers.every(o => !o.active), true);
}
{
    const p = fixture({mode: 'authoring'}); p.flush();
    assert.deepEqual(p.reasons, ['ready']);
    assert.equal(p.appAttrs['data-startup-bypass'], 'true');
}
{
    const p = fixture({mode: 'normal', count: 8, ready: 8, globals: true, alarms: true, time: true});
    p.flush(); assert.equal(p.reasons.length, 0);
    assert.ok(Array.from(p.window.adaIoStartupPending()).includes('areas:8/9'));
}
{
    const p = fixture({route: '/manager'}); p.flush();
    assert.deepEqual(p.reasons, []);
    assert.equal(p.observers.length, 0);
}
{
    const p = fixture({ready: 9, globals: true, alarms: true, time: true});
    p.flush(); assert.deepEqual(p.reasons, ['ready']);
}
{
    const p = fixture({ready: 8, globals: true, alarms: true, time: true});
    p.flush(); assert.deepEqual(p.reasons, []);
    p.replaceApp(); p.flush(); assert.deepEqual(p.reasons, []);
    p.setReady(9); p.flush(); assert.deepEqual(p.reasons, ['ready']);
}
console.log('Startup loader: 12 readiness flags, remount and authoring bypass OK');
