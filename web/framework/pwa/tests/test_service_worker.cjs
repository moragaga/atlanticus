const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '../src/atlanticus/web/pwa/resources/service-worker.js'),
    'utf8'
).replace('__CACHE_NAME__', 'atlanticus-pwa:ada:2');

function response(status = 200, extra = {}) {
    const headers = new Headers(extra.headers || {});
    return {
        status,
        type: extra.type || 'basic',
        headers,
        clone() {
            return response(status, extra);
        },
    };
}

function worker({existing = [], fetcher = async () => response(), failCache = false} = {}) {
    const listeners = new Map();
    const entries = new Map(existing.map((name) => [name, new Map()]));
    const deleted = [];
    let claimed = 0;
    let skipped = 0;
    let networkCalls = 0;
    const caches = {
        async keys() { return [...entries.keys()]; },
        async delete(name) { deleted.push(name); return entries.delete(name); },
        async open(name) {
            if (failCache) throw Error('Cache unavailable');
            if (!entries.has(name)) entries.set(name, new Map());
            const cache = entries.get(name);
            return {
                async match(request) { return cache.get(request.url); },
                async put(request, value) { cache.set(request.url, value); },
            };
        },
    };
    const self = {
        location: {origin: 'https://app.example'},
        clients: {claim: async () => { claimed += 1; }},
        skipWaiting: () => { skipped += 1; },
        addEventListener(name, handler) { listeners.set(name, handler); },
    };
    vm.runInNewContext(source, {
        caches, self, URL, fetch: async (req) => {
            networkCalls += 1;
            return fetcher(req);
        },
    });
    async function dispatch(name, request) {
        const pending = [];
        let promise;
        const event = {
            request,
            waitUntil(value) { pending.push(value); },
            respondWith(value) { promise = value; },
        };
        listeners.get(name)(event);
        if (promise === undefined) {
            await Promise.all(pending);
            return {intercepted: false};
        }
        const result = await promise;
        await Promise.all(pending);
        return {intercepted: true, result};
    }
    return {
        dispatch, entries, deleted,
        get claimed() { return claimed; },
        get skipped() { return skipped; },
        get networkCalls() { return networkCalls; },
    };
}

function request(pathname, options = {}) {
    return new Request(`https://app.example${pathname}`, options);
}

test('activation preserves current and other application caches while removing older versions', async () => {
    const w = worker({existing: [
        'atlanticus-pwa:ada:1', 'atlanticus-pwa:ada:2', 'atlanticus-pwa:other:1',
    ]});
    await w.dispatch('install');
    await w.dispatch('activate');
    assert.equal(w.skipped, 1);
    assert.equal(w.claimed, 1);
    assert.deepEqual(w.deleted, ['atlanticus-pwa:ada:1']);
    assert.deepEqual([...w.entries.keys()], ['atlanticus-pwa:ada:2', 'atlanticus-pwa:other:1']);
});

test('assets are cached and reused without additional network requests', async () => {
    const w = worker();
    const asset = request('/assets/main.css?m=123');
    const first = await w.dispatch('fetch', asset);
    const second = await w.dispatch('fetch', asset);
    assert.equal(first.intercepted, true);
    assert.equal(second.intercepted, true);
    assert.equal(first.result.status, 200);
    assert.equal(w.networkCalls, 1);
    assert.equal(w.entries.get('atlanticus-pwa:ada:2').size, 1);
    await w.dispatch('fetch', request('/assets/main.css?m=124'));
    assert.equal(w.networkCalls, 2);
});

test('navigations and dynamic endpoints are never intercepted', async () => {
    const w = worker();
    const items = [
        request('/'),
        request('/_dash-layout'),
        request('/_dash-dependencies'),
        request('/_dash-update-component'),
        request('/_dash-component-suites/dash/renderer.js'),
        request('/api/data'),
        request('/manifest.webmanifest'),
        new Request('https://other.example/assets/pic.png'),
        request('/assets/asset.png', {method: 'POST'}),
        request('/assets/asset.png', {headers: {Range: 'bytes=0-99'}}),
        request('/assets/asset.png', {headers: {Authorization: 'Bearer abc'}}),
        request('/assets/asset.png', {cache: 'reload'}),
        request('/assets/asset.png', {cache: 'no-store'}),
        request('/assets/asset.png', {cache: 'no-cache'}),
    ];
    for (const item of items) {
        assert.equal((await w.dispatch('fetch', item)).intercepted, false, item.url);
    }
    assert.equal(w.networkCalls, 0);
});

test('failed, private, nonbasic and cookie-setting responses are not cached', async () => {
    const cases = [
        response(404), response(500), response(206),
        response(200, {type: 'opaque'}),
        response(200, {headers: {'Cache-Control': 'private, max-age=3600'}}),
        response(200, {headers: {'Cache-Control': 'no-store'}}),
        response(200, {headers: {'Set-Cookie': 'session=abc'}}),
    ];
    for (const value of cases) {
        const w = worker({fetcher: async () => value});
        await w.dispatch('fetch', request('/assets/image.svg'));
        assert.equal(w.entries.get('atlanticus-pwa:ada:2')?.size || 0, 0);
    }
});

test('offline cached assets work; unavailable network without cache rejects', async () => {
    let offline = false;
    const w = worker({fetcher: async () => {
        if (offline) throw Error('offline');
        return response();
    }});
    await w.dispatch('fetch', request('/assets/a.js'));
    offline = true;
    const cached = await w.dispatch('fetch', request('/assets/a.js'));
    assert.equal(cached.result.status, 200);
    assert.equal(w.networkCalls, 1);
    await assert.rejects(() => w.dispatch('fetch', request('/assets/missing.js')), /offline/);
});

test('Cache API failures do not break retrieval from the network', async () => {
    const w = worker({failCache: true});
    const result = await w.dispatch('fetch', request('/assets/a.js'));
    assert.equal(result.result.status, 200);
    assert.equal(w.networkCalls, 1);
});
