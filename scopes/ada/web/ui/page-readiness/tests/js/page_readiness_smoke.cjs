'use strict';

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const scriptPath = path.join(__dirname, '../../src/ada/web/ui/page_readiness/resources/js/10-page-readiness.js');
const code = fs.readFileSync(scriptPath, 'utf8');

class Node {
    constructor(attrs = {}, classes = []) {
        this.attrs = { ...attrs };
        this.classes = new Set(classes);
        this.children = [];
        this.hidden = false;
        this.listeners = new Map();
        this.parent = null;
    }
    append(child) { child.parent = this; this.children.push(child); return child; }
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    closest(selector) {
        let node = this;
        while (node) {
            if (selector === '[data-ada-page-readiness="true"]' && node.getAttribute('data-ada-page-readiness') === 'true') {
                return node;
            }
            node = node.parent;
        }
        return null;
    }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    removeEventListener(name) { this.listeners.delete(name); }
    emit(name, event) { const callback = this.listeners.get(name); if (callback) callback(event); }
    _descendants() { return this.children.flatMap((child) => [child, ...child._descendants()]); }
    querySelector(selector) {
        if (selector === ':scope > .ada-page-readiness__loader') {
            return this.children.find((child) => child.classes.has('ada-page-readiness__loader')) || null;
        }
        return null;
    }
    querySelectorAll(selector) {
        if (selector === '[data-ada-component-key][data-ada-render-ready]') {
            return this._descendants().filter((node) => node.getAttribute('data-ada-component-key') !== null && node.getAttribute('data-ada-render-ready') !== null);
        }
        return [];
    }
}

const scope = new Node({
    'data-ada-page-readiness': 'true',
    'data-ada-page-readiness-enabled': 'true',
    'data-ada-page-readiness-settle-ms': '160',
    'data-ada-page-readiness-state': 'loading',
    'aria-busy': 'true',
});
const content = scope.append(new Node({}, ['ada-page-readiness__content']));
const loader = scope.append(new Node({}, ['ada-page-readiness__loader']));
const a = content.append(new Node({ 'data-ada-component-key': 'a', 'data-ada-render-ready': 'false' }));
const b = content.append(new Node({ 'data-ada-component-key': 'b', 'data-ada-render-ready': 'false' }));
const nestedScope = content.append(new Node({ 'data-ada-page-readiness': 'true' }));
nestedScope.append(new Node({ 'data-ada-component-key': 'nested', 'data-ada-render-ready': 'false' }));

let observer = null;
let nextTimer = 1;
const timers = new Map();
const document = {
    documentElement: new Node(),
    querySelectorAll(selector) { return selector === '[data-ada-page-readiness="true"]' ? [scope] : []; },
};
class MutationObserver {
    constructor(callback) { observer = callback; }
    observe() {}
}
const window = {
    setTimeout(callback, delay) { const id = nextTimer++; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    requestAnimationFrame(callback) { callback(); },
    getComputedStyle() { return { transitionDuration: '240ms', transitionDelay: '0ms' }; },
};

const context = { window, document, MutationObserver, console, Number, Array, WeakMap, Math, String };
vm.runInNewContext(code, context, { filename: scriptPath });

function triggerMutation() { observer(); }
function runTimerByDelay(delay) {
    const entry = [...timers.entries()].find(([, value]) => value.delay === delay);
    if (!entry) throw new Error(`Missing timer with delay ${delay}`);
    timers.delete(entry[0]);
    entry[1].callback();
}
function assert(value, message) { if (!value) throw new Error(message); }

assert(scope.getAttribute('data-ada-page-readiness-state') === 'loading', 'initial false signals must keep loading');
a.setAttribute('data-ada-render-ready', 'true');
triggerMutation();
assert(scope.getAttribute('data-ada-page-readiness-state') === 'loading', 'partial readiness must keep loading');
b.setAttribute('data-ada-render-ready', 'true');
triggerMutation();
assert(scope.getAttribute('data-ada-page-readiness-state') === 'settling', 'all true must enter settling');

const c = content.append(new Node({ 'data-ada-component-key': 'c', 'data-ada-render-ready': 'false' }));
triggerMutation();
assert(scope.getAttribute('data-ada-page-readiness-state') === 'loading', 'new false signal during settle must cancel readiness');
c.setAttribute('data-ada-render-ready', 'true');
triggerMutation();
runTimerByDelay(160);
assert(scope.getAttribute('data-ada-page-readiness-state') === 'fading', 'stable all true must begin fade');
loader.emit('transitionend', { target: loader, propertyName: 'opacity' });
assert(scope.getAttribute('data-ada-page-readiness-state') === 'ready', 'transition end must finish readiness');
assert(scope.getAttribute('aria-busy') === 'false', 'ready scope must clear aria-busy');
assert(loader.hidden === true, 'loader must be hidden after fade');

b.setAttribute('data-ada-render-ready', 'false');
triggerMutation();
assert(scope.getAttribute('data-ada-page-readiness-state') === 'ready', 'ready must remain latched after periodic changes');

console.log('ADA Page Readiness JS smoke: PASS');
