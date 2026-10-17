const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(
  path.join(__dirname, '../src/ada/web/ui/content_state/resources/js/20-content-state-runtime.js'),
  'utf8',
);

function harness() {
  const listeners = new Map();
  const app = {
    getAttribute(name) {
      return name === 'data-ada-operational-tool-key' ? 'operations' : null;
    },
  };
  const wrappers = [];
  function wrapper(keys, declared = 'ready', operational = true, serverRuntime = 'ready') {
    const attributes = new Map([
      ['data-ada-content-state-runtime', 'true'],
      ['data-ada-content-state-declared', declared],
      ['data-ada-content-state', declared],
    ]);
    if (operational) attributes.set('data-ada-content-state-operational', 'true');
    if (serverRuntime !== 'ready') {
      attributes.set('data-ada-content-state-server-runtime', serverRuntime);
    }
    if (keys !== null) attributes.set('data-ada-content-state-sources', keys.join(','));
    const overlayAttributes = new Map();
    const item = {
      getAttribute(key) { return attributes.get(key) ?? null; },
      hasAttribute(key) { return attributes.has(key); },
      setAttribute(key, value) { attributes.set(key, value); },
      closest() { return app; },
      querySelector() { return { setAttribute(key, value) { overlayAttributes.set(key, value); } }; },
      overlayAttributes,
    };
    wrappers.push(item);
    return item;
  }
  const document = {
    readyState: 'complete',
    body: {},
    addEventListener(event, handler) { listeners.set(event, handler); },
    dispatchEvent(event) { listeners.get(event.type)?.(event); },
    querySelectorAll() { return wrappers; },
  };
  const CustomEvent = class {
    constructor(type, options = {}) { this.type = type; this.detail = options.detail; }
  };
  vm.runInNewContext(source, {
    document,
    CustomEvent,
    MutationObserver: class { observe() {} },
    Element: class {},
  });
  function publish(sourceKey, condition, toolKey = 'operations') {
    document.dispatchEvent(new CustomEvent('ada:source-freshness', {
      detail: { toolKey, sourceKey, condition },
    }));
  }
  return { wrapper, publish };
}

function state(item) {
  return item.getAttribute('data-ada-content-state');
}

test('PI y Dispatch se degradan y recuperan sin afectar otras cards', () => {
  const { wrapper, publish } = harness();
  const pi = wrapper(['pi']);
  const dispatch = wrapper(['dispatch']);
  const mixed = wrapper(['pi', 'dispatch']);
  const independent = wrapper([]);
  const unclassified = wrapper(null);

  publish('pi', 'fresh');
  assert.equal(state(mixed), 'source_error');
  publish('dispatch', 'fresh');
  publish('dispatch', 'hard_stale');
  assert.deepEqual([pi, dispatch, mixed, independent, unclassified].map(state),
    ['ready', 'stale', 'stale', 'ready', 'stale']);

  publish('dispatch', 'fresh');
  assert.deepEqual([pi, dispatch, mixed, independent, unclassified].map(state),
    ['ready', 'ready', 'ready', 'ready', 'ready']);

  publish('pi', 'hard_stale');
  assert.deepEqual([pi, dispatch, mixed, independent, unclassified].map(state),
    ['stale', 'ready', 'stale', 'ready', 'stale']);

  publish('pi', 'fresh');
  assert.deepEqual([pi, dispatch, mixed, independent, unclassified].map(state),
    ['ready', 'ready', 'ready', 'ready', 'ready']);
});

test('DATA_ERROR y CONSTRUCTION conservan su prioridad', () => {
  const { wrapper, publish } = harness();
  const mixed = wrapper(['pi', 'dispatch']);
  const construction = wrapper(['dispatch'], 'construction');
  const invalidKpi = wrapper(['pi'], 'ready', true, 'source_error');
  publish('pi', 'fresh');
  publish('dispatch', 'data_error');
  assert.equal(state(mixed), 'source_error');
  assert.equal(state(construction), 'construction');
  assert.equal(state(invalidKpi), 'source_error');
  publish('dispatch', 'fresh');
  assert.equal(state(mixed), 'ready');
  assert.equal(state(construction), 'construction');
  assert.equal(state(invalidKpi), 'source_error');
});

test('las fuentes de otro Tool no modifican las cards', () => {
  const { wrapper, publish } = harness();
  const pi = wrapper(['pi']);
  publish('pi', 'fresh');
  publish('pi', 'hard_stale', 'other');
  assert.equal(state(pi), 'ready');
});

test('un wrapper padre no altera el overlay del indicador anidado', () => {
  const { wrapper, publish } = harness();
  const parent = wrapper(['dispatch']);
  const child = wrapper(['pi']);
  const childOverlay = child.overlayAttributes;
  parent.querySelector = (selector) => {
    if (selector === ':scope > .ada-content-state__overlay') {
      return { setAttribute(key, value) { parent.overlayAttributes.set(key, value); } };
    }
    return { setAttribute(key, value) { childOverlay.set(key, value); } };
  };

  publish('dispatch', 'hard_stale');
  assert.equal(state(parent), 'stale');
  assert.equal(parent.overlayAttributes.get('aria-hidden'), 'false');
  assert.equal(childOverlay.get('aria-hidden'), undefined);
});
