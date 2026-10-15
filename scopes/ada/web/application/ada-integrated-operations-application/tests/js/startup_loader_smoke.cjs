const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
    path.resolve(__dirname, '../../src/ada/web/application/integrated_operations/modules/dashboard/resources/js/05_startup_loader.js'),
    'utf8'
);

function setup({ location = '/', alarm = 'false', global = true, sectors = 9, populated = true } = {}) {
    let callback;
    let disconnected = false;
    const frames = [];
    const classes = new Set();
    const overlay = {
        classList: {
            contains: (value) => classes.has(value),
            add: (value) => classes.add(value),
        },
        setAttribute(name, value) {
            this[name] = value;
        },
    };
    const dashboard = {
        dataset: { adaIoAlarmReady: alarm },
        closest: () => ({ querySelector: () => global ? ({}) : null }),
        querySelectorAll: () => Array.from({ length: sectors }, () => ({
            querySelector: () => ({ childNodes: populated ? [{}] : [] }),
        })),
    };
    const document = {
        documentElement: {},
        getElementById: (id) => id === 'ada-io-startup-loader' ? overlay : dashboard,
    };
    const context = {
        document,
        location: { pathname: location },
        window: { requestAnimationFrame: (fn) => { frames.push(fn); } },
        MutationObserver: class {
            constructor(fn) { callback = fn; }
            observe() {}
            disconnect() { disconnected = true; }
        },
    };
    vm.runInNewContext(script, context);
    const flush = () => {
        while (frames.length) frames.shift()();
    };
    return {
        overlay,
        dashboard,
        flush,
        notify: () => callback?.(),
        hidden: () => classes.has('ada-io-startup-loader--exit'),
        disconnected: () => disconnected,
    };
}

{
    const page = setup({ alarm: 'true' });
    page.flush();
    assert.equal(page.hidden(), true);
    assert.equal(page.disconnected(), true);
    assert.equal(page.overlay['aria-hidden'], 'true');
}

{
    const page = setup({ alarm: 'false' });
    page.flush();
    assert.equal(page.hidden(), false);
    page.dashboard.dataset.adaIoAlarmReady = 'true';
    page.notify();
    page.flush();
    assert.equal(page.hidden(), true);
}

for (const missing of [{ global: false }, { sectors: 8 }, { populated: false }]) {
    const page = setup({ alarm: 'true', ...missing });
    page.flush();
    assert.equal(page.hidden(), false);
}

{
    const page = setup({ alarm: 'false' });
    page.flush();
    page.overlay.classList.add('ada-io-startup-loader--exit');
    page.notify();
    page.flush();
    assert.equal(page.disconnected(), true);
}

{
    const page = setup({ location: '/manager', alarm: 'true' });
    page.flush();
    assert.equal(page.hidden(), false);
}

console.log('Startup loader readiness: OK');
