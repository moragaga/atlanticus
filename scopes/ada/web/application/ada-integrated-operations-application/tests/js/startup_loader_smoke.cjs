const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.resolve(
    __dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/js/05_startup_loader.js'
), 'utf8');
const css = fs.readFileSync(path.resolve(
    __dirname,
    '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/css/05_startup_loader.css'
), 'utf8');

function setup({ location = '/', global = true, sectors = 9, ready = 9, alarmRender = false } = {}) {
    const frames = [];
    const observers = [];
    const completed = [];
    const areas = Array.from({ length: sectors }, (_, index) => ({
        getAttribute(name) {
            if (name === 'data-ready') return index < ready ? 'true' : 'false';
            if (name === 'data-ada-io-component-key') return 'area_' + index;
            return null;
        },
    }));
    const app = { querySelector: () => global ? ({}) : null };
    const dashboard = {
        closest: () => app,
        querySelectorAll: () => areas,
    };
    const globalSlot = {};
    const board = {
        style: { getPropertyValue: () => alarmRender ? '1' : '' },
    };
    const overlay = {};
    const idMap = {
        'ada-io-startup-loader': overlay,
        'ada-integrated-operations-dashboard': dashboard,
        'ada-operational-header-global-indicators-slot': globalSlot,
        'ada-alarm-live-board': board,
    };
    const document = {
        body: {},
        getElementById: (id) => idMap[id] || null,
    };
    const window = {
        requestAnimationFrame: (fn) => frames.push(fn),
        adaIoFinishStartupLoader: (reason) => {
            completed.push(reason);
            window.adaIoStopStartupObservers?.();
        },
    };
    class Observer {
        constructor(fn) {
            this.fn = fn;
            this.active = false;
            this.options = null;
            observers.push(this);
        }
        observe(target, options) {
            this.active = true;
            this.target = target;
            this.options = options;
        }
        disconnect() { this.active = false; }
    }
    vm.runInNewContext(script, {
        document, window, location: { pathname: location }, MutationObserver: Observer,
    });
    function flush() {
        while (frames.length) frames.shift()();
    }
    function notify(target, attribute) {
        observers.filter((o) => o.active && o.target === target &&
            (!attribute || o.options.attributeFilter?.includes(attribute)))
            .forEach((o) => o.fn());
    }
    return {
        areas, board, dashboard, globalSlot, observers, completed, window, flush, notify,
        setAreaReady: (amount) => {
            ready = amount;
            notify(dashboard, 'data-ready');
        },
        setAlarmRendered: () => {
            alarmRender = true;
            notify(board, 'style');
        },
        setGlobalRendered: () => {
            global = true;
            notify(globalSlot);
        },
    };
}

{
    const page = setup({ alarmRender: true });
    page.flush();
    assert.deepEqual(page.completed, ['ready']);
    assert.equal(page.observers.every((observer) => !observer.active), true);
}

{
    const page = setup({ alarmRender: false });
    page.flush();
    assert.deepEqual(page.completed, []);
    assert.deepEqual(Array.from(page.window.adaIoStartupPending()), ['alarms_render']);
    page.setAlarmRendered();
    page.flush();
    assert.deepEqual(page.completed, ['ready']);
}

{
    const page = setup({ sectors: 9, ready: 7, alarmRender: true });
    page.flush();
    assert.deepEqual(Array.from(page.window.adaIoStartupPending()), ['area_7', 'area_8']);
    page.setAreaReady(9);
    page.flush();
    assert.deepEqual(page.completed, ['ready']);
}

{
    const page = setup({ global: false, alarmRender: true });
    page.flush();
    assert.deepEqual(Array.from(page.window.adaIoStartupPending()), ['global_indicators']);
    page.setGlobalRendered();
    page.flush();
    assert.deepEqual(page.completed, ['ready']);
}

{
    const page = setup({ sectors: 8, alarmRender: true });
    page.flush();
    assert.equal(page.completed.length, 0);
    assert.ok(Array.from(page.window.adaIoStartupPending()).includes('areas:8/9'));
}

{
    const page = setup({ location: '/manager', alarmRender: true });
    page.flush();
    assert.deepEqual(page.completed, []);
    assert.equal(page.observers.length, 0);
}

{
    const page = setup({ ready: 5, alarmRender: false });
    page.flush();
    const discovery = page.observers[0];
    assert.equal(discovery.active, false);
    assert.equal(page.observers[1].options.attributeFilter.join(','), 'data-ready');
    assert.equal(page.observers[3].options.attributeFilter.join(','), 'style');
}

assert.match(css, /html\[data-ada-io-loader-active='true'\]/);
assert.match(css, /overflow: hidden !important/);
assert.match(css, /transform: scale\(0\)/);
assert.match(css, /transition: opacity 500ms/);
console.log('Startup loader behavior: OK');
