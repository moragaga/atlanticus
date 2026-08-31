'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        '../../src/ada/web/application/generic/resources/wake_lock/js/10-screen-wake-lock.js',
    ),
    'utf8',
);

function createEventTarget() {
    const listeners = new Map();
    return {
        addEventListener(name, callback) {
            const entries = listeners.get(name) || [];
            entries.push(callback);
            listeners.set(name, entries);
        },
        dispatchEvent(event) {
            for (const callback of listeners.get(event.type) || []) {
                callback(event);
            }
        },
        emit(name) {
            this.dispatchEvent({ type: name });
        },
    };
}

function createSentinel() {
    const target = createEventTarget();
    let releases = 0;
    const sentinel = {
        released: false,
        addEventListener: target.addEventListener,
        async release() {
            if (!sentinel.released) {
                sentinel.released = true;
                releases += 1;
                target.emit('release');
            }
        },
        browserRelease() {
            if (!sentinel.released) {
                sentinel.released = true;
                target.emit('release');
            }
        },
        releaseCount() {
            return releases;
        },
    };
    return sentinel;
}

async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

function createHarness({ pathname = '/', visibilityState = 'visible', supported = true, reject = null } = {}) {
    const documentTarget = createEventTarget();
    const windowTarget = createEventTarget();
    const warnings = [];
    const errors = [];
    const requests = [];
    const sentinels = [];
    const location = { pathname };
    const history = {
        pushState(_state, _unused, url) {
            if (typeof url === 'string') {
                location.pathname = url;
            }
        },
        replaceState(_state, _unused, url) {
            if (typeof url === 'string') {
                location.pathname = url;
            }
        },
    };
    const navigator = {};
    if (supported) {
        navigator.wakeLock = {
            async request(kind) {
                requests.push(kind);
                if (reject) {
                    throw reject;
                }
                const sentinel = createSentinel();
                sentinels.push(sentinel);
                return sentinel;
            },
        };
    }
    const document = {
        readyState: 'complete',
        visibilityState,
        addEventListener: documentTarget.addEventListener,
    };
    const window = {
        location,
        history,
        addEventListener: windowTarget.addEventListener,
        dispatchEvent: windowTarget.dispatchEvent,
    };
    const context = vm.createContext({
        console: {
            warn(...args) {
                warnings.push(args);
            },
            error(...args) {
                errors.push(args);
            },
        },
        document,
        window,
        navigator,
        Event: class Event {
            constructor(type) {
                this.type = type;
            }
        },
        Object,
        Promise,
    });
    vm.runInContext(source, context);

    return {
        async flush() {
            await flush();
        },
        requestCount() {
            return requests.length;
        },
        warnings,
        errors,
        history,
        setVisibility(value) {
            document.visibilityState = value;
            documentTarget.emit('visibilitychange');
        },
        pageshow() {
            windowTarget.emit('pageshow');
        },
        currentRequestKinds() {
            return [...requests];
        },
        sentinelCount() {
            return sentinels.length;
        },
        releaseCount(index) {
            return sentinels[index].releaseCount();
        },
        browserRelease(index) {
            sentinels[index].browserRelease();
        },
    };
}

(async () => {
    {
        const harness = createHarness();
        await harness.flush();
        assert.equal(harness.requestCount(), 1);
        assert.deepEqual(harness.currentRequestKinds(), ['screen']);
        assert.equal(harness.errors.length, 0);
        assert.equal(harness.warnings.length, 0);
    }

    {
        const harness = createHarness({ supported: false });
        await harness.flush();
        assert.equal(harness.requestCount(), 0);
        assert.equal(harness.warnings.length, 1);
        assert.equal(harness.errors.length, 0);
        harness.pageshow();
        await harness.flush();
        assert.equal(harness.warnings.length, 1);
    }

    {
        const harness = createHarness({ reject: new Error('denied') });
        await harness.flush();
        assert.equal(harness.requestCount(), 1);
        assert.equal(harness.errors.length, 1);
    }

    {
        const harness = createHarness({ reject: new Error('hidden-race') });
        harness.setVisibility('hidden');
        await harness.flush();
        assert.equal(harness.requestCount(), 1);
        assert.equal(harness.errors.length, 0);
    }

    {
        const harness = createHarness({ visibilityState: 'hidden' });
        await harness.flush();
        assert.equal(harness.requestCount(), 0);
        harness.setVisibility('visible');
        await harness.flush();
        assert.equal(harness.requestCount(), 1);
        harness.setVisibility('hidden');
        await harness.flush();
        assert.equal(harness.releaseCount(0), 1);
        harness.setVisibility('visible');
        await harness.flush();
        assert.equal(harness.requestCount(), 2);
    }

    {
        const harness = createHarness();
        await harness.flush();
        assert.equal(harness.sentinelCount(), 1);
        harness.browserRelease(0);
        await harness.flush();
        assert.equal(harness.warnings.length, 1);
        assert.equal(harness.requestCount(), 1);
        harness.pageshow();
        await harness.flush();
        assert.equal(harness.requestCount(), 2);
    }

    {
        const harness = createHarness({ pathname: '/manager' });
        await harness.flush();
        assert.equal(harness.requestCount(), 0);
        harness.history.pushState({}, '', '/');
        await harness.flush();
        assert.equal(harness.requestCount(), 1);
        harness.history.pushState({}, '', '/manager');
        await harness.flush();
        assert.equal(harness.releaseCount(0), 1);
        harness.history.replaceState({}, '', '/');
        await harness.flush();
        assert.equal(harness.requestCount(), 2);
    }

    console.log('ADA Wake Lock JS smoke: PASS');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
