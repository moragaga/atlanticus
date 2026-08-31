'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        '../../src/ada/web/application/generic/resources/session/js/10-session-auto-reload.js',
    ),
    'utf8',
);

function createHarness({ pathname = '/', visibilityState = 'visible' } = {}) {
    let now = 0;
    let reloads = 0;
    let nextTimerId = 0;
    const timers = new Map();
    const listeners = new Map();
    const marker = {
        dataset: {
            reloadAfterMs: '1000',
            checkEveryMs: '100',
        },
    };
    const document = {
        readyState: 'complete',
        visibilityState,
        getElementById(id) {
            return id === 'ada-session-auto-reload' ? marker : null;
        },
        addEventListener(name, callback) {
            listeners.set(name, callback);
        },
    };
    const location = {
        pathname,
        reload() {
            reloads += 1;
        },
    };
    const window = {
        location,
        setTimeout(callback, delay) {
            const id = ++nextTimerId;
            timers.set(id, { callback, at: now + delay });
            return id;
        },
    };
    const DateFake = {
        now() {
            return now;
        },
    };
    const context = vm.createContext({
        document,
        window,
        Date: DateFake,
        Number,
        Math,
    });
    vm.runInContext(source, context);

    const advanceTo = (target) => {
        while (true) {
            const due = [...timers.entries()]
                .filter(([, timer]) => timer.at <= target)
                .sort((left, right) => left[1].at - right[1].at)[0];
            if (!due) {
                break;
            }
            const [id, timer] = due;
            timers.delete(id);
            now = timer.at;
            timer.callback();
        }
        now = target;
    };

    return {
        advanceTo,
        setPathname(value) {
            location.pathname = value;
        },
        setVisibility(value) {
            document.visibilityState = value;
            const listener = listeners.get('visibilitychange');
            if (listener) {
                listener();
            }
        },
        reloadCount() {
            return reloads;
        },
        pendingTimers() {
            return [...timers.values()];
        },
    };
}

{
    const harness = createHarness();
    harness.advanceTo(999);
    assert.equal(harness.reloadCount(), 0);
    harness.advanceTo(1000);
    assert.equal(harness.reloadCount(), 1);
}

{
    const harness = createHarness({ visibilityState: 'hidden' });
    harness.advanceTo(1500);
    assert.equal(harness.reloadCount(), 0);
    assert.ok(harness.pendingTimers().every((timer) => timer.at >= 1500));
    harness.setVisibility('visible');
    assert.equal(harness.reloadCount(), 1);
}

{
    const harness = createHarness({ pathname: '/manager' });
    harness.advanceTo(1500);
    assert.equal(harness.reloadCount(), 0);
    harness.setPathname('/');
    harness.advanceTo(1600);
    assert.equal(harness.reloadCount(), 1);
}

{
    const harness = createHarness({ pathname: '/manager', visibilityState: 'hidden' });
    harness.advanceTo(1500);
    harness.setVisibility('visible');
    assert.equal(harness.reloadCount(), 0);
}

console.log('ADA Session auto-reload JS smoke: PASS');
