from __future__ import annotations

from types import SimpleNamespace

from atlanticus.web.application import run_web_application
from atlanticus.web.configuration import WebEnvironment


def test_flask_server_uses_8000_by_default() -> None:
    received = []
    runtime = SimpleNamespace(
        server=SimpleNamespace(run=lambda **values: received.append(values)),
        environment=WebEnvironment.LOCAL,
    )

    run_web_application(runtime)

    assert received == [
        {'host': '0.0.0.0', 'port': 8000, 'debug': True, 'use_reloader': True}
    ]


def test_flask_server_uses_supplied_port() -> None:
    received = []
    runtime = SimpleNamespace(
        server=SimpleNamespace(run=lambda **values: received.append(values)),
        environment=WebEnvironment.LOCAL,
    )

    run_web_application(runtime, port=8051)

    assert received[0]['port'] == 8051
