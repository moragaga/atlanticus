from __future__ import annotations

import shutil
import subprocess

import pytest
from dash import Output

from ada.web.shell.navigation.callbacks import register_ada_navigation_callbacks
from ada.web.shell.navigation.ids import AdaNavigationIds

_NODE_SCENARIOS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8');
const noUpdate = Symbol('no_update');
const sandbox = {window: {dash_clientside: {callback_context: null, no_update: noUpdate}}};
const toggle = vm.runInNewContext('(' + source + ')', sandbox);
function invoke(changedKeys, mobile, desktop, path, open, lastPath) {
    const triggered = changedKeys.map(key => ({
        prop_id: key, value: key.endsWith('.n_clicks') ? 1 : path,
    }));
    sandbox.window.dash_clientside.callback_context = {
        triggered: triggered,
        triggered_id: triggered.length ? triggered[0].prop_id.split('.')[0] : null,
    };
    return Array.from(toggle(mobile, desktop, path, open, lastPath));
}
const mobileClick = 'ada-navigation-mobile-toggle.n_clicks';
const desktopClick = 'ada-navigation-desktop-toggle.n_clicks';
const locationChange = 'ada-navigation-location.pathname';
assert.deepEqual(invoke([], 0, 0, '/', false, null), [noUpdate, '/']);
assert.deepEqual(invoke([locationChange], 0, 0, '/', false, null), [noUpdate, '/']);
assert.deepEqual(invoke([desktopClick], 0, 1, '/', false, '/'), [true, noUpdate]);
assert.deepEqual(invoke([locationChange], 0, 1, '/', true, '/'), [noUpdate, noUpdate]);
assert.deepEqual(invoke([desktopClick], 0, 2, '/', true, '/'), [false, noUpdate]);
assert.deepEqual(invoke([mobileClick], 1, 0, '/', false, '/'), [true, noUpdate]);
assert.deepEqual(invoke([locationChange], 1, 0, '/other', true, '/'), [false, '/other']);
assert.deepEqual(invoke([locationChange, desktopClick], 0, 1, '/', false, null), [true, '/']);
assert.deepEqual(invoke([desktopClick], 0, 0, '/', false, '/'), [noUpdate, noUpdate]);
"""


class _ClientsideCollector:
    def __init__(self) -> None:
        self.toggle: str | None = None
        self.prevent_initial_call: bool | None = None

    def clientside_callback(self, source: str, *dependencies: object, **options: object) -> None:
        for item in dependencies:
            if (
                isinstance(item, Output)
                and item.component_id == AdaNavigationIds.OFFCANVAS
                and item.component_property == 'is_open'
            ):
                self.toggle = source
                self.prevent_initial_call = options.get('prevent_initial_call') is True
                break


def test_client_first_click_and_real_navigation_change() -> None:
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for clientside interaction qualification')
    collected = _ClientsideCollector()
    register_ada_navigation_callbacks(collected, None)
    assert collected.toggle is not None
    assert collected.prevent_initial_call is False
    result = subprocess.run(
        (node, '-e', _NODE_SCENARIOS),
        input=collected.toggle,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
