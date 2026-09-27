from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest
from dash import Dash, html
from flask import Flask

from atlanticus.web.application import _AtlanticusDash
from atlanticus.web.dash_worker import prepare_dash_worker


def _new_dash() -> _AtlanticusDash:
    server = Flask(__name__)
    dash = _AtlanticusDash(__name__, server=server, use_pages=False)
    dash.layout = html.Div('Ready')
    return dash


def test_each_worker_registers_component_resources_before_first_http_request():
    workers = [_new_dash() for _ in range(3)]

    for dash in workers:
        prepare_dash_worker(dash)
        assert dash.registered_paths.get('dash')

    with workers[0].server.test_request_context('/'):
        index = workers[0].index()
    match = re.search(r'src="([^"]*/_dash-component-suites/dash/[^"]+\.js)"', index)
    assert match is not None
    path = match.group(1)

    for dash in workers:
        response = dash.server.test_client().get(path)
        assert response.status_code == 200
        assert 'javascript' in response.content_type


def test_dash_server_initialization_is_serial_under_parallel_first_requests(monkeypatch):
    dash = _new_dash()
    dash.server.add_url_rule('/smoke', 'smoke', lambda: 'ok')
    barrier = Barrier(2)
    guard = Lock()
    active = 0
    maximum = 0
    original = Dash._setup_server

    def observed_setup(instance):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.04)
            return original(instance)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(Dash, '_setup_server', observed_setup)

    def request():
        barrier.wait(timeout=5)
        return dash.server.test_client().get('/smoke').status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _index: request(), range(2)))

    assert results == (200, 200)
    assert maximum == 1


def test_dash_preparation_rejects_non_dash_objects():
    with pytest.raises(TypeError, match='Dash worker preparation'):
        prepare_dash_worker(object())
